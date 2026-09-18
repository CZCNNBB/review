from pydantic import BaseModel
from typing import Optional, Generic, TypeVar

# 定义泛型类型变量T，用于在类定义中表示任意类型
T = TypeVar("T")

# 定义统一响应模型，继承自BaseModel并实现泛型支持
class Result(BaseModel, Generic[T]):
    """
    全局统一响应模型
    用于标准化所有API接口的返回格式
    
    泛型设计允许我们指定data字段的具体类型，提供类型安全
    例如：Result[str] 表示data字段是字符串类型
    """
    code: int   # 业务状态码，0表示成功，其他值表示不同的错误类型
    msg: str     # 响应消息，用于描述操作结果  
    data: Optional[T] = None     # 默认值为None，表示如果没有数据返回，这个字段就是None

    @classmethod    # classmethod代表这是一个类方法，而不是实例方法，区别在于类方法可以直接通过类名调用，而实例方法必须通过实例调用(不用定义类的对象，而可以直接调用)
    def success(cls, data: Optional[T] = None) -> "Result[T]":
        """
        类方法：创建成功响应实例

        参数:
            data: 要返回的数据，可选参数，默认为None

        返回:
            Result[T]: 包含成功状态码和数据的响应对象
        """
        return cls(code=0, msg="success", data=data)


    @classmethod
    def fail(cls, code: int, msg: str) -> "Result[None]":
        """
        类方法：创建失败响应实例
        
        参数:
            code: 错误状态码，用于区分不同类型的错误
            msg: 错误消息，描述具体的错误原因

        返回:
            Result[None]: 包含错误信息的响应对象，data字段固定为None
        """
        return cls(code=code, msg=msg, data=None)
    