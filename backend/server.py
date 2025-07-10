from fastapi import FastAPI, APIRouter, HTTPException, Depends
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

# Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    full_name: str
    phone: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    phone: str

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
    
    # Create default checking account
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

@api_router.get("/")
async def root():
    return {"message": "SeuBank API - Professional Banking Platform"}

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

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()