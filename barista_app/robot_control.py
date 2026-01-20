"""
Robot Control Board Serial Client Integration.
Adapted from the original backend_robot_control.py module.
"""
import threading
import time
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SerialNotConnectedError(Exception):
    """Raised when trying to communicate on a closed serial port."""
    pass


class SerialProtocolError(Exception):
    """Raised when the board returns an error or unexpected response."""
    pass


@dataclass(frozen=True)
class JobCommand:
    """Immutable value-object representing one drink job."""
    dose_g: float       # 0.1 – 200.0 g
    grind_grade: int    # 1 – 10
    recipe_no: int      # 1 – 4


class RobotControlBoardSerialClient:
    """
    Thread-safe serial interface to the Robot Control Board.
    """

    _MIN_DOSE, _MAX_DOSE = 0.1, 200.0
    _MIN_GRADE, _MAX_GRADE = 1, 10
    _MIN_RECIPE, _MAX_RECIPE = 1, 4

    def __init__(
        self,
        port: str = "COM7",
        baudrate: int = 115_200,
        read_timeout_s: float = 1.5,
        write_timeout_s: float = 1.5,
        ack_timeout_s: float = 2.0,
        newline: bytes = b"\n",
    ):
        self._port = port
        self._baudrate = baudrate
        self._read_timeout = read_timeout_s
        self._write_timeout = write_timeout_s
        self._ack_timeout = ack_timeout_s
        self._newline = newline
        self._serial = None
        self._lock = threading.Lock()
        self._connected = False

    def connect(self) -> None:
        """Open the serial port."""
        try:
            import serial
            with self._lock:
                if self._serial and self._serial.is_open:
                    return
                self._serial = serial.Serial(
                    port=self._port,
                    baudrate=self._baudrate,
                    timeout=self._read_timeout,
                    write_timeout=self._write_timeout,
                )
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
                time.sleep(0.15)
                self._connected = True
                logger.info(f"Connected to robot on {self._port}")
        except ImportError:
            logger.warning("PySerial not installed, using mock mode")
            self._connected = False
        except Exception as e:
            logger.error(f"Failed to connect to robot: {e}")
            self._connected = False
            raise SerialNotConnectedError(f"Cannot connect to {self._port}: {e}")

    def close(self) -> None:
        """Close the serial port gracefully."""
        with self._lock:
            if self._serial and self._serial.is_open:
                self._serial.close()
            self._serial = None
            self._connected = False
            logger.info("Disconnected from robot")

    def is_connected(self) -> bool:
        """Return True if serial port is open."""
        return self._connected and self._serial is not None and self._serial.is_open

    def _require_serial(self):
        if not self.is_connected():
            raise SerialNotConnectedError("Serial port not connected")

    def _validate_job(self, dose_g: float, grind_grade: int, recipe_no: int) -> None:
        if not (self._MIN_DOSE <= dose_g <= self._MAX_DOSE):
            raise ValueError(f"dose_g must be {self._MIN_DOSE}–{self._MAX_DOSE}")
        if not (self._MIN_GRADE <= grind_grade <= self._MAX_GRADE):
            raise ValueError(f"grind_grade must be {self._MIN_GRADE}–{self._MAX_GRADE}")
        if not (self._MIN_RECIPE <= recipe_no <= self._MAX_RECIPE):
            raise ValueError(f"recipe_no must be {self._MIN_RECIPE}–{self._MAX_RECIPE}")

    def _format_job_line(self, cmd: JobCommand) -> bytes:
        line = f"JOB,{cmd.dose_g:.2f},{cmd.grind_grade},{cmd.recipe_no}"
        return line.encode("ascii") + self._newline

    def _readline_until_deadline(self, deadline: float) -> Optional[bytes]:
        while time.monotonic() < deadline:
            line = self._serial.readline()
            if line:
                return line.strip()
            time.sleep(0.05)
        return None

    def send_job(self, dose_g: float, grind_grade: int, recipe_no: int) -> str:
        """
        Send a drink job to the robot board.
        Returns 'ACK' on success, raises SerialProtocolError on failure.
        """
        self._validate_job(dose_g, grind_grade, recipe_no)
        cmd = JobCommand(dose_g, grind_grade, recipe_no)

        with self._lock:
            self._require_serial()
            tx_line = self._format_job_line(cmd)
            self._serial.write(tx_line)
            logger.info(f"Sent: {tx_line.decode().strip()}")
            self._serial.flush()  # Ensure data is sent immediately
            deadline = time.monotonic() + self._ack_timeout
            response = self._readline_until_deadline(deadline)

            if response is None:
                raise SerialProtocolError("Timeout waiting for ACK/ERR")

            response_str = response.decode("ascii", errors="replace")
            logger.info(f"Received: {response_str}")

            if response_str.upper() == "ACK":
                return "ACK"
            elif response_str.upper().startswith("ERR"):
                raise SerialProtocolError(f"Robot error: {response_str}")
            else:
                raise SerialProtocolError(f"Unexpected response: {response_str}")

    def get_status(self) -> str:
        """Request status from the robot."""
        with self._lock:
            self._require_serial()
            self._serial.write(b"STATUS" + self._newline)
            deadline = time.monotonic() + self._ack_timeout
            response = self._readline_until_deadline(deadline)
            self._serial.flush()  # Ensure data is sent immediately
            if response:
                return response.decode("ascii", errors="replace")
            raise SerialProtocolError("Timeout waiting for status response")


# Global singleton instance
_robot_client: Optional[RobotControlBoardSerialClient] = None
_robot_lock = threading.Lock()


def is_demo_mode() -> bool:
    """Check if running in demo mode (no physical robot)."""
    from django.conf import settings
    return getattr(settings, 'ROBOT_DEMO_MODE', True)


def get_robot_client() -> RobotControlBoardSerialClient:
    """Get or create the global robot client instance."""
    global _robot_client
    with _robot_lock:
        if _robot_client is None:
            from django.conf import settings
            port = getattr(settings, 'ROBOT_SERIAL_PORT', 'COM7')
            baudrate = getattr(settings, 'ROBOT_BAUDRATE', 115200)
            _robot_client = RobotControlBoardSerialClient(port=port, baudrate=baudrate)
        return _robot_client


def send_manual_order(dose_g: float, grind_grade: int, recipe_no: int) -> tuple[bool, str]:
    """
    Send a manual order to the robot.
    Returns (success: bool, message: str)
    """
    # Demo mode - simulate successful order
    if is_demo_mode():
        logger.info(f"[DEMO] Simulating order: {dose_g}g, grade {grind_grade}, recipe {recipe_no}")
        time.sleep(0.5)  # Simulate processing time
        return True, "ACK (Demo Mode)"

    client = get_robot_client()

    # Check if connected, try to connect if not
    if not client.is_connected():
        try:
            client.connect()
        except SerialNotConnectedError as e:
            return False, f"Robot not connected: {e}"

    try:
        result = client.send_job(dose_g, grind_grade, recipe_no)
        return True, result
    except SerialProtocolError as e:
        return False, str(e)
    except SerialNotConnectedError as e:
        return False, str(e)
    except Exception as e:
        logger.exception("Unexpected error sending order")
        return False, f"Unexpected error: {e}"


def check_robot_connection() -> tuple[bool, str]:
    """Check if robot is connected and responsive."""
    # Demo mode - always connected
    if is_demo_mode():
        return True, "Demo Mode - Simulated Connection"

    client = get_robot_client()

    if not client.is_connected():
        try:
            client.connect()
        except SerialNotConnectedError:
            return False, "Not connected"

    try:
        status = client.get_status()
        return True, status
    except (SerialProtocolError, SerialNotConnectedError) as e:
        return False, str(e)
    except Exception as e:
        return False, f"Error: {e}"
