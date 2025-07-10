#!/usr/bin/env python3
"""
SeuBank Backend API Testing Suite
Tests all banking features comprehensively
"""

import requests
import json
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv(Path(__file__).parent / 'frontend' / '.env')

# Get backend URL from environment
BACKEND_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001')
API_BASE = f"{BACKEND_URL}/api"

print(f"Testing SeuBank API at: {API_BASE}")

class SeuBankTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.user_data = {
            "email": "maria.silva@email.com",
            "password": "MinhaSenh@123",
            "full_name": "Maria Silva Santos",
            "phone": "+55 11 99999-8888"
        }
        self.login_data = {
            "email": "maria.silva@email.com", 
            "password": "MinhaSenh@123"
        }
        self.user_accounts = []
        
    def set_auth_header(self, token):
        """Set authorization header for authenticated requests"""
        self.auth_token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        
    def test_user_registration(self):
        """Test user registration endpoint"""
        print("\n=== Testing User Registration ===")
        
        try:
            response = self.session.post(f"{API_BASE}/auth/register", json=self.user_data)
            print(f"Registration Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Registration successful")
                print(f"Token type: {data.get('token_type')}")
                print(f"Access token received: {'Yes' if data.get('access_token') else 'No'}")
                
                # Set auth token for subsequent requests
                if data.get('access_token'):
                    self.set_auth_header(data['access_token'])
                    
                return True
            elif response.status_code == 400:
                print("⚠️  User already exists (expected if running multiple times)")
                return "user_exists"
            else:
                print(f"❌ Registration failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Registration error: {str(e)}")
            return False
    
    def test_user_login(self):
        """Test user login endpoint"""
        print("\n=== Testing User Login ===")
        
        try:
            response = self.session.post(f"{API_BASE}/auth/login", json=self.login_data)
            print(f"Login Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Login successful")
                print(f"Token type: {data.get('token_type')}")
                print(f"Access token received: {'Yes' if data.get('access_token') else 'No'}")
                
                # Set auth token for subsequent requests
                if data.get('access_token'):
                    self.set_auth_header(data['access_token'])
                    
                return True
            else:
                print(f"❌ Login failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return False
    
    def test_get_user_profile(self):
        """Test user profile retrieval"""
        print("\n=== Testing User Profile ===")
        
        if not self.auth_token:
            print("❌ No auth token available")
            return False
            
        try:
            response = self.session.get(f"{API_BASE}/profile")
            print(f"Profile Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Profile retrieved successfully")
                print(f"User ID: {data.get('id')}")
                print(f"Email: {data.get('email')}")
                print(f"Full Name: {data.get('full_name')}")
                print(f"Phone: {data.get('phone')}")
                return True
            else:
                print(f"❌ Profile retrieval failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Profile error: {str(e)}")
            return False
    
    def test_get_accounts(self):
        """Test account retrieval"""
        print("\n=== Testing Account Retrieval ===")
        
        if not self.auth_token:
            print("❌ No auth token available")
            return False
            
        try:
            response = self.session.get(f"{API_BASE}/accounts")
            print(f"Accounts Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Accounts retrieved successfully")
                print(f"Number of accounts: {len(data)}")
                
                for account in data:
                    print(f"  - Account ID: {account.get('id')}")
                    print(f"    Account Number: {account.get('account_number')}")
                    print(f"    Type: {account.get('account_type')}")
                    print(f"    Balance: R$ {account.get('balance', 0):.2f}")
                    
                self.user_accounts = data
                return True
            else:
                print(f"❌ Account retrieval failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Account retrieval error: {str(e)}")
            return False
    
    def test_create_account(self):
        """Test account creation"""
        print("\n=== Testing Account Creation ===")
        
        if not self.auth_token:
            print("❌ No auth token available")
            return False
            
        try:
            account_data = {"account_type": "savings"}
            response = self.session.post(f"{API_BASE}/accounts", json=account_data)
            print(f"Account Creation Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Savings account created successfully")
                print(f"Account ID: {data.get('id')}")
                print(f"Account Number: {data.get('account_number')}")
                print(f"Type: {data.get('account_type')}")
                print(f"Balance: R$ {data.get('balance', 0):.2f}")
                return True
            else:
                print(f"❌ Account creation failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Account creation error: {str(e)}")
            return False
    
    def test_deposit_money(self):
        """Test money deposit"""
        print("\n=== Testing Money Deposit ===")
        
        if not self.auth_token or not self.user_accounts:
            print("❌ No auth token or accounts available")
            return False
            
        try:
            account_id = self.user_accounts[0]['id']
            deposit_data = {
                "to_account_id": account_id,
                "amount": 1500.00,
                "transaction_type": "deposit",
                "description": "Depósito inicial para conta"
            }
            
            response = self.session.post(f"{API_BASE}/transactions/deposit", json=deposit_data)
            print(f"Deposit Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Deposit successful")
                print(f"Message: {data.get('message')}")
                print(f"New Balance: R$ {data.get('new_balance', 0):.2f}")
                return True
            else:
                print(f"❌ Deposit failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Deposit error: {str(e)}")
            return False
    
    def test_withdraw_money(self):
        """Test money withdrawal"""
        print("\n=== Testing Money Withdrawal ===")
        
        if not self.auth_token or not self.user_accounts:
            print("❌ No auth token or accounts available")
            return False
            
        try:
            account_id = self.user_accounts[0]['id']
            withdraw_data = {
                "to_account_id": account_id,
                "amount": 300.00,
                "transaction_type": "withdrawal",
                "description": "Saque para despesas pessoais"
            }
            
            response = self.session.post(f"{API_BASE}/transactions/withdrawal", json=withdraw_data)
            print(f"Withdrawal Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Withdrawal successful")
                print(f"Message: {data.get('message')}")
                print(f"New Balance: R$ {data.get('new_balance', 0):.2f}")
                return True
            else:
                print(f"❌ Withdrawal failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Withdrawal error: {str(e)}")
            return False
    
    def test_insufficient_funds_withdrawal(self):
        """Test withdrawal with insufficient funds"""
        print("\n=== Testing Insufficient Funds Withdrawal ===")
        
        if not self.auth_token or not self.user_accounts:
            print("❌ No auth token or accounts available")
            return False
            
        try:
            account_id = self.user_accounts[0]['id']
            withdraw_data = {
                "to_account_id": account_id,
                "amount": 50000.00,  # Large amount to trigger insufficient funds
                "transaction_type": "withdrawal",
                "description": "Teste de saldo insuficiente"
            }
            
            response = self.session.post(f"{API_BASE}/transactions/withdrawal", json=withdraw_data)
            print(f"Insufficient Funds Test Status: {response.status_code}")
            
            if response.status_code == 400:
                print("✅ Insufficient funds error handled correctly")
                print(f"Error message: {response.json().get('detail', 'No detail')}")
                return True
            else:
                print(f"❌ Expected 400 error but got: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Insufficient funds test error: {str(e)}")
            return False
    
    def test_transfer_money(self):
        """Test money transfer between accounts"""
        print("\n=== Testing Money Transfer ===")
        
        if not self.auth_token or len(self.user_accounts) < 2:
            print("❌ Need at least 2 accounts for transfer test")
            return False
            
        try:
            from_account_id = self.user_accounts[0]['id']
            to_account_id = self.user_accounts[1]['id']
            
            transfer_data = {
                "from_account_id": from_account_id,
                "to_account_id": to_account_id,
                "amount": 250.00,
                "description": "Transferência entre contas próprias"
            }
            
            response = self.session.post(f"{API_BASE}/transactions/transfer", json=transfer_data)
            print(f"Transfer Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Transfer successful")
                print(f"Message: {data.get('message')}")
                print(f"New From Balance: R$ {data.get('new_from_balance', 0):.2f}")
                return True
            else:
                print(f"❌ Transfer failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Transfer error: {str(e)}")
            return False
    
    def test_get_transactions(self):
        """Test transaction history retrieval"""
        print("\n=== Testing Transaction History ===")
        
        if not self.auth_token:
            print("❌ No auth token available")
            return False
            
        try:
            response = self.session.get(f"{API_BASE}/transactions")
            print(f"Transaction History Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print("✅ Transaction history retrieved successfully")
                print(f"Number of transactions: {len(data)}")
                
                for i, transaction in enumerate(data[:5]):  # Show first 5 transactions
                    print(f"  Transaction {i+1}:")
                    print(f"    ID: {transaction.get('id')}")
                    print(f"    Type: {transaction.get('transaction_type')}")
                    print(f"    Amount: R$ {transaction.get('amount', 0):.2f}")
                    print(f"    Description: {transaction.get('description')}")
                    print(f"    Timestamp: {transaction.get('timestamp')}")
                    
                return True
            else:
                print(f"❌ Transaction history failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Transaction history error: {str(e)}")
            return False
    
    def test_unauthorized_access(self):
        """Test unauthorized access to protected endpoints"""
        print("\n=== Testing Unauthorized Access ===")
        
        # Create session without auth token
        unauth_session = requests.Session()
        
        try:
            response = unauth_session.get(f"{API_BASE}/profile")
            print(f"Unauthorized Profile Access Status: {response.status_code}")
            
            if response.status_code == 403 or response.status_code == 401:
                print("✅ Unauthorized access properly blocked")
                return True
            else:
                print(f"❌ Expected 401/403 but got: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Unauthorized access test error: {str(e)}")
            return False
    
    def run_all_tests(self):
        """Run all backend API tests"""
        print("🏦 Starting SeuBank Backend API Tests")
        print("=" * 50)
        
        results = {}
        
        # Test registration or login
        reg_result = self.test_user_registration()
        if reg_result == "user_exists":
            # User exists, try login instead
            results['login'] = self.test_user_login()
        else:
            results['registration'] = reg_result
        
        # Test authenticated endpoints
        results['profile'] = self.test_get_user_profile()
        results['get_accounts'] = self.test_get_accounts()
        results['create_account'] = self.test_create_account()
        
        # Refresh accounts after creation
        self.test_get_accounts()
        
        # Test transactions
        results['deposit'] = self.test_deposit_money()
        results['withdrawal'] = self.test_withdraw_money()
        results['insufficient_funds'] = self.test_insufficient_funds_withdrawal()
        
        # Test transfer if we have multiple accounts
        if len(self.user_accounts) >= 2:
            results['transfer'] = self.test_transfer_money()
        
        results['transaction_history'] = self.test_get_transactions()
        results['unauthorized_access'] = self.test_unauthorized_access()
        
        # Print summary
        print("\n" + "=" * 50)
        print("🏦 SeuBank Backend API Test Summary")
        print("=" * 50)
        
        passed = 0
        total = 0
        
        for test_name, result in results.items():
            total += 1
            if result:
                passed += 1
                print(f"✅ {test_name.replace('_', ' ').title()}: PASSED")
            else:
                print(f"❌ {test_name.replace('_', ' ').title()}: FAILED")
        
        print(f"\nOverall Result: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed! SeuBank backend is working correctly.")
        else:
            print("⚠️  Some tests failed. Check the detailed output above.")
        
        return results

if __name__ == "__main__":
    tester = SeuBankTester()
    tester.run_all_tests()