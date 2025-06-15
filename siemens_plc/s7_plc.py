"""PLC drive."""
import logging
import os
import pathlib
from logging.handlers import TimedRotatingFileHandler

from typing import Union, Optional
from threading import Lock

import snap7
from snap7 import util

from siemens_plc.exception import PLCReadError, PLCWriteError


# pylint: disable=too-many-arguments, too-many-positional-arguments, too-many-instance-attributes
class S7PLC:
    """This class provides methods for interacting with a Siemens S7 PLC using the Snap7 library."""
    LOG_FORMAT = "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"

    def __init__(self, ip: str, rack: int = 0, slot: int = 1, plc_name: str = ""):
        """Initialize the S7Plc class.

        Args:
            ip: plc ip address.
            rack: rack number.
            slot: slot number.
            plc_name: plc name.
        """
        logging.basicConfig(level=logging.INFO, encoding="UTF-8", format=self.LOG_FORMAT)

        self.ip = ip
        self.plc_name = plc_name if plc_name else ip
        self.rack = rack
        self.slot = slot
        self._s7_client = snap7.client.Client()
        self.plc_lock = Lock()

        self.logger = logging.getLogger(__name__)
        self._file_handler = None  # 保存日志的处理器
        self._initial_log_config()

    def _initial_log_config(self) -> None:
        """日志配置."""
        self._create_log_dir()
        self.logger.addHandler(self.file_handler)  # handler_passive 日志保存到统一文件

    @staticmethod
    def _create_log_dir():
        """判断log目录是否存在, 不存在就创建."""
        log_dir = pathlib.Path(f"{os.getcwd()}/log")
        if not log_dir.exists():
            os.mkdir(log_dir)

    @property
    def file_handler(self) -> TimedRotatingFileHandler:
        """设置保存日志的处理器, 每隔 24h 自动生成一个日志文件.

        Returns:
            TimedRotatingFileHandler: 返回 TimedRotatingFileHandler 日志处理器.
        """
        if self._file_handler is None:
            self._file_handler = TimedRotatingFileHandler(
                f"{os.getcwd()}/log/plc_{self.plc_name}.log",
                when="D", interval=1, backupCount=10, encoding="UTF-8"
            )
            self._file_handler.namer = self._custom_log_name
            self._file_handler.setFormatter(logging.Formatter(self.LOG_FORMAT))
        return self._file_handler

    def _custom_log_name(self, log_path: str):
        """自定义新生成的日志名称.

        Args:
            log_path: 原始的日志文件路径.

        Returns:
            str: 新生成的自定义日志文件路径.
        """
        _, suffix, date_str = log_path.split(".")
        new_log_path = f"{os.getcwd()}/log/plc_{self.plc_name}_{date_str}.{suffix}"
        return new_log_path

    def communication_open(self):
        """Connect to a PLC.

        Raises:
            PLCConnectError: If there is an error in the connection process.
        """
        if not self.get_connect_state():
            try:
                self._s7_client.connect(self.ip, self.rack, self.slot)
                self.logger.info("PLC: Connected successfully")
                return True
            except RuntimeError as e:
                self.logger.error("PLC: Connection error: %s", str(e))
                return False
        return True

    def disconnect(self) -> None:
        """Disconnect from the PLC."""
        if self.get_connect_state():
            self._s7_client.disconnect()
            self.logger.info("PLC: Disconnected successfully")

    def get_connect_state(self) -> bool:
        """Get connect to plc state.

        Returns:
            bool: True is connected, False is not connected.
        """
        if self._s7_client.get_connected():
            self.logger.info("Plc connected state is True")
            return True
        return False

    def execute_read(
            self, data_type: str, address: int, db_num: int, size: int, bit_index: int = 0, save_log: bool = True
    ) -> Union[str, bool, int]:
        """读取plc数据的通用方法.

        Args:
            data_type (str): 读取数据的类型.
            db_num (int): db num.
            address (int): 开始地址位.
            size (int): 地址位长度.
            bit_index (int): bool类型对应的bool index, 默认为0.
            save_log: 是否保存日志, 默认保存.

        Returns:
            Union[str, bool, int]: 返回读取plc读取的数据.
        """
        with self.plc_lock:
            read_func = getattr(self, f"read_{data_type}_data")
            if data_type == "bool":
                return read_func(db_num, address, size, bit_index, save_log)
            return read_func(db_num, address, size, save_log)

    def read_int_data(self, db_number: int, start: int, size: int = 2, save_log: bool = True) -> int:
        """Read integer data from the PLC.

        Args:
            db_number (int): Number of the DB to be read.
            start (int): Byte index to start reading from.
            size (int): Amount of bytes to be read.
            save_log: 是否保存日志, 默认保存.

        Returns:
            int: Status of the read integer data operation.

        Raises:
            PLCReadError: If reading integer type data fails.
        """
        response_data = self._s7_client.db_read(db_number, start, size)
        if not response_data:
            raise PLCReadError("PLC: Read integer data error")
        value = util.get_int(response_data, 0)
        if save_log:
            self.logger.info("读取 int 地址 %s 的值是: %s, 读取长度为 %s", start, value, size)
        return value

    def read_real_data(self, db_number: int, start: int, size: int = 4, save_log: bool = True) -> float:
        """Read real data from the PLC.

        Args:
            db_number (int): Number of the DB to be read.
            start (int): Byte index to start reading from.
            size (int): Amount of bytes to be read.
            save_log: 是否保存日志, 默认保存.

        Returns:
            int: Value of the read real data operation.

        Raises:
            PLCReadError: If reading real type data fails.
        """
        response_data = self._s7_client.db_read(db_number, start, size)
        if not response_data:
            raise PLCReadError("PLC: Read real data error")
        value = util.get_real(response_data, 0)
        if save_log:
            self.logger.info("读取 real 地址 %s 的值是: %s, 读取长度为 %s", start, value, size)
        return value

    def read_lreal_data(self, db_number: int, start: int, size: int = 8, save_log: bool = True) -> float:
        """Read lreal data from the PLC.

        Args:
            db_number (int): Number of the DB to be read.
            start (int): Byte index to start reading from.
            size (int): Amount of bytes to be read.
            save_log: 是否保存日志, 默认保存.

        Returns:
            int: Value of the read lreal data operation.

        Raises:
            PLCReadError: If reading lreal type data fails.
        """
        response_data = self._s7_client.db_read(db_number, start, size)
        if not response_data:
            raise PLCReadError("PLC: Read lreal data error")
        value = util.get_lreal(response_data, 0)
        if save_log:
            self.logger.info("读取 lreal 地址 %s 的值是: %s, 读取长度为 %s", start, value, size)
        return value

    def read_bool_data(
            self, db_number: int, start: int, size: int = 1, bool_index: int = 0, save_log: bool = True
    ) -> bool:
        """Read bool data from the PLC.

        Args:
            db_number (int): Number of the DB to be read.
            start (int): Byte index to start reading from.
            size (int): Amount of bytes to be read.
            bool_index (int): bit index to read from.
            save_log: 是否保存日志, 默认保存.

        Returns:
            bool: Status of the read bool data operation.

        Raises:
            PLCReadError: If reading bool type data fails.
        """
        response_data = self._s7_client.db_read(db_number, start, size)
        if not response_data:
            raise PLCReadError("PLC: Read bool data error")
        value = util.get_bool(response_data, 0, bool_index)
        if save_log:
            self.logger.info("读取 lreal 地址 %s 的值是: %s, 读取长度为 %s, bit 位是: %s", start, value, size, bool_index)
        return value

    def read_str_data(self, db_number: int, start: int, size: int, save_log: bool = True) -> str:
        """Read string data from the PLC.

        Args:
            db_number (int): Number of the DB to be read.
            start (int): Byte index to start reading from.
            size (int): Amount of bytes to be read.
            save_log: 是否保存日志, 默认保存.

        Returns:
            int: Status of the read string data operation.

        Raises:
            PLCReadError: If reading string type data fails.
        """
        real_size = size + 2
        response_data = self._s7_client.db_read(db_number, start, real_size)
        if not response_data:
            raise PLCReadError("PLC: Read string data error")
        value = util.get_string(response_data, 0).strip()
        if save_log:
            self.logger.info("读取 str 地址 %s 的值是: %s, 读取长度为 %s", start, value, size)
        return value

    def execute_write(
            self, data_type, address: int, db_num: int, value: Union[str, bool, int, float],
            bit_index: int = 0, size=None
    ) -> int:
        """写入plc数据的通用方法.

        Args:
            data_type (str): 读取数据的类型.
            db_num (int): db num.
            address (int): 开始地址位.
            value (Union[str, bool, int]): 要写入的数据.
            bit_index (int): bool类型对应的bool index.
            size: 写入数据的长度.

        Returns:
            int: 写入后的code.
        """
        with self.plc_lock:
            write_func = getattr(self, f"write_{data_type}_data")
            if data_type == "bool":
                return write_func(db_num, address, value, bit_index)
            if data_type == "str":
                return write_func(db_num, address, value, size)
            return write_func(db_num, address, value)

    def write_int_data(self, db_number: int, start: int, data: int):
        """Write integer data to the PLC.

        Args:
            db_number (int): Number of the DB to be written.
            start (int): Byte index to start writing to.
            data (int): The value to be written.

        Returns:
            int: Status of the write integer data operation.

        Raises:
            PLCWriteError: If writing integer type data fails.
        """
        try:
            int_data_bytearray = bytearray(self._s7_client.db_read(db_number, start, 2))
            int_data_bytearray = util.set_int(int_data_bytearray, 0, data)
            return self._s7_client.db_write(db_number, start, int_data_bytearray)
        except RuntimeError as e:
            raise PLCWriteError("PLC: Write integer data error") from e

    def write_real_data(self, db_number: int, start: int, data: float) -> Optional[int]:
        """Write real data to the PLC.

        Args:
            db_number (int): Number of the DB to be written.
            start (int): Byte index to start writing to.
            data (int): The value to be written.

        Returns:
            Optional[int]: Status of the write real data operation.

        Raises:
            PLCWriteError: If writing real type data fails.
        """
        try:
            real_data_bytearray = bytearray(self._s7_client.db_read(db_number, start, 4))
            real_data_bytearray = util.set_real(real_data_bytearray, 0, data)
            return self._s7_client.db_write(db_number, start, real_data_bytearray)
        except RuntimeError as e:
            raise PLCWriteError("PLC: Write real data error") from e

    def write_lreal_data(self, db_number: int, start: int, data: float) -> Optional[int]:
        """Write lreal data to the PLC.

        Args:
            db_number (int): Number of the DB to be written.
            start (int): Byte index to start writing to.
            data (int): The value to be written.

        Returns:
            Optional[int]: Status of the write lreal data operation.

        Raises:
            PLCWriteError: If writing lreal type data fails.
        """
        try:
            lreal_data_bytearray = bytearray(self._s7_client.db_read(db_number, start, 8))
            lreal_data_bytearray = util.set_lreal(lreal_data_bytearray, 0, data)
            return self._s7_client.db_write(db_number, start, lreal_data_bytearray)
        except RuntimeError as e:
            raise PLCWriteError("PLC: Write lreal data error") from e

    def write_bool_data(self, db_number: int, start: int, data: bool, bool_index: int):
        """Write bool data to the PLC.

        Args:
            db_number (int): Number of the DB to be written.
            start (int): Byte index to start writing to.
            data (bool): The value to be written.
            bool_index (int): bit index to read from, The range is 0-7.

        Returns:
            int: Status of the write string data operation.

        Raises:
            PLCWriteError: If writing bool type data fails.
        """
        try:
            bool_data_bytearray = bytearray(self._s7_client.db_read(db_number, start, 1))
            bool_data_bytearray = util.set_bool(bool_data_bytearray, 0, bool_index, data)
            return self._s7_client.db_write(db_number, start, bool_data_bytearray)
        except RuntimeError as e:
            raise PLCWriteError("PLC: Write bool data error") from e

    def write_str_data(self, db_number: int, start: int, data: str, size: int):
        """Write string data to the PLC.

        Args:
            db_number: Number of the DB to be written.
            start: Byte index to start writing to.
            data: The value to be written.
            size: 写入字符串长度.

        Returns:
            int: Status of the write string data operation.

        Raises:
            PLCWriteError: If writing string type data fails.
        """
        try:
            str_data = bytearray(
                int.to_bytes(size, 1, "big") +
                int.to_bytes(len(data), 1, "big") +
                data.encode(encoding="ascii")
            )
            return self._s7_client.db_write(db_number, start, str_data)
        except RuntimeError as e:
            raise PLCWriteError("PLC: Write string data error") from e
