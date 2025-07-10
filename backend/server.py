from fastapi import FastAPI, APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timedelta
import bcrypt
import jwt
from decimal import Decimal
import enum

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# JWT Configuration
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Security
security = HTTPBearer()

# Enums
class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"

class AccountType(str, enum.Enum):
    CHECKING = "checking"
    SAVINGS = "savings"

class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"

# Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    full_name: str
    phone: str
    role: UserRole = UserRole.USER
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    phone: str
    role: UserRole = UserRole.USER

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None

class AdminUserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    phone: str
    role: UserRole

class UserLogin(BaseModel):
    email: str
    password: str

class Account(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    account_number: str = Field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    account_type: AccountType
    balance: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

class AccountCreate(BaseModel):
    account_type: AccountType

class Transaction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_account_id: Optional[str] = None
    to_account_id: Optional[str] = None
    amount: float
    transaction_type: TransactionType
    description: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: str

class TransactionCreate(BaseModel):
    to_account_id: Optional[str] = None
    amount: float
    transaction_type: TransactionType
    description: str

class TransferRequest(BaseModel):
    from_account_id: str
    to_account_id: str
    amount: float
    description: str

class Token(BaseModel):
    access_token: str
    token_type: str

class AdminStats(BaseModel):
    total_users: int
    total_accounts: int
    total_transactions: int
    total_balance: float
    active_users: int
    recent_transactions: int

class UserWithAccounts(BaseModel):
    user: User
    accounts: List[Account]
    total_balance: float
    transaction_count: int

# Helper Functions
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        user = await db.users.find_one({"email": email})
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return User(**user)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

async def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# Create default admin user on startup
async def create_default_admin():
    admin_email = "admin@seubank.com"
    existing_admin = await db.users.find_one({"email": admin_email})
    
    if not existing_admin:
        admin_data = {
            "email": admin_email,
            "password": "admin123",
            "full_name": "SeuBank Administrator",
            "phone": "+55 11 99999-0000",
            "role": UserRole.ADMIN
        }
        
        hashed_password = hash_password(admin_data["password"])
        user_dict = admin_data.copy()
        user_dict.pop("password")
        user_dict["hashed_password"] = hashed_password
        user_obj = User(**user_dict)
        
        await db.users.insert_one(user_obj.dict())
        print(f"✅ Default admin created: {admin_email} / admin123")

# Auth Routes
@api_router.post("/auth/register", response_model=Token)
async def register(user_data: UserCreate):
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    hashed_password = hash_password(user_data.password)
    user_dict = user_data.dict()
    user_dict.pop("password")
    user_dict["hashed_password"] = hashed_password
    user_obj = User(**user_dict)
    
    await db.users.insert_one(user_obj.dict())
    
    # Create default checking account for regular users
    if user_obj.role == UserRole.USER:
        account = Account(user_id=user_obj.id, account_type=AccountType.CHECKING)
        await db.accounts.insert_one(account.dict())
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_obj.email}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@api_router.post("/auth/login", response_model=Token)
async def login(user_credentials: UserLogin):
    user = await db.users.find_one({"email": user_credentials.email})
    if not user or not verify_password(user_credentials.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

# Account Routes
@api_router.get("/accounts", response_model=List[Account])
async def get_accounts(current_user: User = Depends(get_current_user)):
    accounts = await db.accounts.find({"user_id": current_user.id}).to_list(100)
    return [Account(**account) for account in accounts]

@api_router.post("/accounts", response_model=Account)
async def create_account(account_data: AccountCreate, current_user: User = Depends(get_current_user)):
    account = Account(user_id=current_user.id, account_type=account_data.account_type)
    await db.accounts.insert_one(account.dict())
    return account

@api_router.get("/accounts/{account_id}", response_model=Account)
async def get_account(account_id: str, current_user: User = Depends(get_current_user)):
    account = await db.accounts.find_one({"id": account_id, "user_id": current_user.id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return Account(**account)

# Transaction Routes
@api_router.get("/transactions", response_model=List[Transaction])
async def get_transactions(current_user: User = Depends(get_current_user)):
    transactions = await db.transactions.find({"user_id": current_user.id}).sort("timestamp", -1).to_list(100)
    return [Transaction(**transaction) for transaction in transactions]

@api_router.post("/transactions/deposit")
async def deposit_money(transaction_data: TransactionCreate, current_user: User = Depends(get_current_user)):
    if transaction_data.transaction_type != TransactionType.DEPOSIT:
        raise HTTPException(status_code=400, detail="Invalid transaction type")
    
    # Get account
    account = await db.accounts.find_one({"id": transaction_data.to_account_id, "user_id": current_user.id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Update account balance
    new_balance = account["balance"] + transaction_data.amount
    await db.accounts.update_one(
        {"id": transaction_data.to_account_id}, 
        {"$set": {"balance": new_balance}}
    )
    
    # Create transaction record
    transaction = Transaction(
        to_account_id=transaction_data.to_account_id,
        amount=transaction_data.amount,
        transaction_type=TransactionType.DEPOSIT,
        description=transaction_data.description,
        user_id=current_user.id
    )
    await db.transactions.insert_one(transaction.dict())
    
    return {"message": "Deposit successful", "new_balance": new_balance}

@api_router.post("/transactions/withdrawal")
async def withdraw_money(transaction_data: TransactionCreate, current_user: User = Depends(get_current_user)):
    if transaction_data.transaction_type != TransactionType.WITHDRAWAL:
        raise HTTPException(status_code=400, detail="Invalid transaction type")
    
    # Get account
    account = await db.accounts.find_one({"id": transaction_data.to_account_id, "user_id": current_user.id})
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Check sufficient balance
    if account["balance"] < transaction_data.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    
    # Update account balance
    new_balance = account["balance"] - transaction_data.amount
    await db.accounts.update_one(
        {"id": transaction_data.to_account_id}, 
        {"$set": {"balance": new_balance}}
    )
    
    # Create transaction record
    transaction = Transaction(
        from_account_id=transaction_data.to_account_id,
        amount=transaction_data.amount,
        transaction_type=TransactionType.WITHDRAWAL,
        description=transaction_data.description,
        user_id=current_user.id
    )
    await db.transactions.insert_one(transaction.dict())
    
    return {"message": "Withdrawal successful", "new_balance": new_balance}

@api_router.post("/transactions/transfer")
async def transfer_money(transfer_data: TransferRequest, current_user: User = Depends(get_current_user)):
    # Get from account
    from_account = await db.accounts.find_one({"id": transfer_data.from_account_id, "user_id": current_user.id})
    if not from_account:
        raise HTTPException(status_code=404, detail="From account not found")
    
    # Get to account
    to_account = await db.accounts.find_one({"id": transfer_data.to_account_id})
    if not to_account:
        raise HTTPException(status_code=404, detail="To account not found")
    
    # Check sufficient balance
    if from_account["balance"] < transfer_data.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    
    # Update balances
    new_from_balance = from_account["balance"] - transfer_data.amount
    new_to_balance = to_account["balance"] + transfer_data.amount
    
    await db.accounts.update_one(
        {"id": transfer_data.from_account_id}, 
        {"$set": {"balance": new_from_balance}}
    )
    await db.accounts.update_one(
        {"id": transfer_data.to_account_id}, 
        {"$set": {"balance": new_to_balance}}
    )
    
    # Create transaction record
    transaction = Transaction(
        from_account_id=transfer_data.from_account_id,
        to_account_id=transfer_data.to_account_id,
        amount=transfer_data.amount,
        transaction_type=TransactionType.TRANSFER,
        description=transfer_data.description,
        user_id=current_user.id
    )
    await db.transactions.insert_one(transaction.dict())
    
    return {"message": "Transfer successful", "new_from_balance": new_from_balance}

# User Profile Routes
@api_router.get("/profile", response_model=User)
async def get_profile(current_user: User = Depends(get_current_user)):
    return current_user

# Admin Routes
@api_router.get("/admin/stats", response_model=AdminStats)
async def get_admin_stats(current_admin: User = Depends(get_current_admin)):
    # Get statistics
    total_users = await db.users.count_documents({})
    total_accounts = await db.accounts.count_documents({})
    total_transactions = await db.transactions.count_documents({})
    active_users = await db.users.count_documents({"is_active": True})
    
    # Get recent transactions count (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_transactions = await db.transactions.count_documents({"timestamp": {"$gte": seven_days_ago}})
    
    # Calculate total balance across all accounts
    accounts = await db.accounts.find({}).to_list(1000)
    total_balance = sum(account["balance"] for account in accounts)
    
    return AdminStats(
        total_users=total_users,
        total_accounts=total_accounts,
        total_transactions=total_transactions,
        total_balance=total_balance,
        active_users=active_users,
        recent_transactions=recent_transactions
    )

@api_router.get("/admin/users", response_model=List[UserWithAccounts])
async def get_all_users(current_admin: User = Depends(get_current_admin)):
    users = await db.users.find({}).to_list(1000)
    result = []
    
    for user_data in users:
        user = User(**user_data)
        # Get user's accounts
        accounts = await db.accounts.find({"user_id": user.id}).to_list(100)
        accounts_list = [Account(**account) for account in accounts]
        
        # Calculate total balance
        total_balance = sum(account.balance for account in accounts_list)
        
        # Get transaction count
        transaction_count = await db.transactions.count_documents({"user_id": user.id})
        
        result.append(UserWithAccounts(
            user=user,
            accounts=accounts_list,
            total_balance=total_balance,
            transaction_count=transaction_count
        ))
    
    return result

@api_router.get("/admin/users/{user_id}", response_model=UserWithAccounts)
async def get_user_by_id(user_id: str, current_admin: User = Depends(get_current_admin)):
    user_data = await db.users.find_one({"id": user_id})
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = User(**user_data)
    # Get user's accounts
    accounts = await db.accounts.find({"user_id": user.id}).to_list(100)
    accounts_list = [Account(**account) for account in accounts]
    
    # Calculate total balance
    total_balance = sum(account.balance for account in accounts_list)
    
    # Get transaction count
    transaction_count = await db.transactions.count_documents({"user_id": user.id})
    
    return UserWithAccounts(
        user=user,
        accounts=accounts_list,
        total_balance=total_balance,
        transaction_count=transaction_count
    )

@api_router.put("/admin/users/{user_id}", response_model=User)
async def update_user(user_id: str, user_update: UserUpdate, current_admin: User = Depends(get_current_admin)):
    user_data = await db.users.find_one({"id": user_id})
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update user data
    update_data = {k: v for k, v in user_update.dict().items() if v is not None}
    if update_data:
        await db.users.update_one({"id": user_id}, {"$set": update_data})
    
    # Return updated user
    updated_user = await db.users.find_one({"id": user_id})
    return User(**updated_user)

@api_router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, current_admin: User = Depends(get_current_admin)):
    user_data = await db.users.find_one({"id": user_id})
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Don't allow deletion of admin users
    if user_data.get("role") == UserRole.ADMIN:
        raise HTTPException(status_code=400, detail="Cannot delete admin users")
    
    # Delete user's accounts and transactions
    await db.accounts.delete_many({"user_id": user_id})
    await db.transactions.delete_many({"user_id": user_id})
    
    # Delete user
    await db.users.delete_one({"id": user_id})
    
    return {"message": "User deleted successfully"}

@api_router.post("/admin/users", response_model=User)
async def create_user_admin(user_data: AdminUserCreate, current_admin: User = Depends(get_current_admin)):
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    hashed_password = hash_password(user_data.password)
    user_dict = user_data.dict()
    user_dict.pop("password")
    user_dict["hashed_password"] = hashed_password
    user_obj = User(**user_dict)
    
    await db.users.insert_one(user_obj.dict())
    
    # Create default checking account for regular users
    if user_obj.role == UserRole.USER:
        account = Account(user_id=user_obj.id, account_type=AccountType.CHECKING)
        await db.accounts.insert_one(account.dict())
    
    return user_obj

@api_router.get("/admin/transactions", response_model=List[Transaction])
async def get_all_transactions(
    current_admin: User = Depends(get_current_admin),
    limit: int = Query(100, le=1000),
    skip: int = Query(0, ge=0)
):
    transactions = await db.transactions.find({}).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)
    return [Transaction(**transaction) for transaction in transactions]

@api_router.get("/admin/transactions/{transaction_id}", response_model=Transaction)
async def get_transaction_by_id(transaction_id: str, current_admin: User = Depends(get_current_admin)):
    transaction = await db.transactions.find_one({"id": transaction_id})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return Transaction(**transaction)

@api_router.get("/")
async def root():
    return {"message": "SeuBank API - Professional Banking Platform with Admin Panel"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    await create_default_admin()

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()