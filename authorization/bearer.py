from typing import Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

app = FastAPI()

# ================= 配置部分 =================
# 生产环境中，SECRET_KEY 应该保存在环境变量中，不要写死在代码里
SECRET_KEY = "my_super_secret_key_change_this_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# 密码哈希工具
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 核心：定义Bearer 认证方案
# tokenUrl="token"告诉FastAPI(以及Swagger UI):
#"如果用户没有Token，引导去'/token'这个接口登录获取"
oauth2_schema = OAuth2PasswordBearer(tokenUrl="token")

# ===============模拟数据库==================


class Token(BaseModel):
    access_token:str
    token_type:str

class User(BaseModel):
    username:str
    email:  Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None

# ===============工具函数==================
def verify_password(plain_password,hashed_password):
    return pwd_context.verify(plain_password + hashed_password)

def create_access_token(data:dict,expires_delta:Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    #将过期时间放入Payload
    to_encode.update({"exp":expire})
    #生成 JWT
    encoded_jwt = jwt.encode(to_encode,SECRET_KEY,algorithm=ALGORITHM)
    return encoded_jwt

# ===============核心依赖项==================
#这里是Bearer认证的核心
#1、token:str = Depends(oauth2_scheme)会自动做以下几件事
#       - 检查请求头是否有 Authorization：Bearer <token>
#       - 解析出token字符串
#       - 如果没有Header 或格式不对，直接抛出异常
async def get_current_user(token:str = Depends(oauth2_schema)):
    credentials_exception = HTTPException(
        status_code = status.HTTP_401_UNAUTHORIZED,
        detail  = "Could not validate credentials",
        headers = {"WWW-Authenticate": "Bearer"},
    )
    try:
        # 解码 JWT
        payload = jwt.decode(token,SECRET_KEY, algorithms = [ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception









