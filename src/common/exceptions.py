"""
自定义异常模块
定义项目中使用的所有自定义异常
"""


class ZZTXBaseException(Exception):
    """项目基础异常类"""
    pass


class ERPAPIException(ZZTXBaseException):
    """ERP API 调用异常"""

    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class DatabaseException(ZZTXBaseException):
    """数据库操作异常"""
    pass


class ConfigException(ZZTXBaseException):
    """配置相关异常"""
    pass


class SyncException(ZZTXBaseException):
    """数据同步异常"""
    pass


class ReportException(ZZTXBaseException):
    """报表生成异常"""
    pass
