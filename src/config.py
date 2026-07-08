from zoneinfo import ZoneInfo

from flask import Flask
from flask_restx import Api
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///asmt2.db'

# optional
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 用户登录 use jwt

# jwt 保存
app.config['JWT_SECRET_KEY'] = 'super-secret-key-for-assignment'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = False
app.config['RESTX_MASK_SWAGGER'] = False

# 初始化数据库
db = SQLAlchemy(app)
# 初始化 jwt
jwt = JWTManager(app)

authorizations = {
    'Bearer': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description':"Enter: Bearer <your_token>",
    }
}

api=Api(
    app, 
    version='1.0', 
    title='Assignment 2 API',
    description='RESTful API for movie data with Admin/User roles',
    authorizations=authorizations,
    security='Bearer',
)

# set timezone
SYDNEY_TZ = ZoneInfo('Australia/Sydney')