"""
Robot Control Board Serial Client Integration.
Adapted from the original backend_robot_control.py module.
"""
import threading
import time
from dataclasses import dataclass
from typing import Optional
import socket
from contextlib import closing
import logging
import traceback

# Configure logging with more detail for debugging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class SerialNotConnectedError(Exception):
    """Raised when trying to communicate on a closed serial port."""
    pass


class SerialProtocolError(Exception):
    """Raised when the board returns an error or unexpected response."""
    pass


@dataclass(frozen=True)
class JobCommand:
    """Immutable value-object representing one drink job."""
    dose_g: int         # 1 – 200 g
    grind_grade: int    # 1 – 11
    doser_no: int       # 1 – 4
    recipe_no: int      # 1 – 4


class RobotControlBoardSerialClient:
    """
    Thread-safe serial interface to the Robot Control Board.
    """

    _MIN_DOSE, _MAX_DOSE = 1, 100
    _MIN_GRADE, _MAX_GRADE = 1, 11
    _MIN_DOSER, _MAX_DOSER = 1, 4
    _MIN_RECIPE, _MAX_RECIPE = 1, 4

    def __init__(
        self,
        port: str = "COM6",
        baudrate: int = 115_200,
        read_timeout_s: float = 3,
        write_timeout_s: float = 3,
        ack_timeout_s: float = 20,
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
        logger.debug(f"[DEBUG] connect() called - attempting to connect to {self._port}")
        logger.debug(f"[DEBUG] Current state: _serial={self._serial}, _connected={self._connected}")

        try:
            import serial
            import serial.tools.list_ports

            # List available ports for debugging
            available_ports = list(serial.tools.list_ports.comports())
            logger.debug(f"[DEBUG] Available serial ports: {[p.device for p in available_ports]}")
            for port_info in available_ports:
                logger.debug(f"[DEBUG]   Port: {port_info.device}, Desc: {port_info.description}, HWID: {port_info.hwid}")

            with self._lock:
                if self._serial and self._serial.is_open:
                    logger.debug(f"[DEBUG] Serial already open, skipping reconnect")
                    return

                logger.debug(f"[DEBUG] Creating Serial object with port={self._port}, baudrate={self._baudrate}")
                logger.debug(f"[DEBUG] Timeouts: read={self._read_timeout}s, write={self._write_timeout}s")

                self._serial = serial.Serial(
                    port=self._port,
                    baudrate=self._baudrate,
                    timeout=self._read_timeout,
                    write_timeout=self._write_timeout,
                )

                logger.debug(f"[DEBUG] Serial object created successfully")
                logger.debug(f"[DEBUG] Serial is_open: {self._serial.is_open}")
                logger.debug(f"[DEBUG] Serial port name: {self._serial.name}")
                logger.debug(f"[DEBUG] Serial settings: {self._serial.get_settings()}")

                logger.debug(f"[DEBUG] Resetting input buffer...")
                self._serial.reset_input_buffer()
                logger.debug(f"[DEBUG] Resetting output buffer...")
                self._serial.reset_output_buffer()

                logger.debug(f"[DEBUG] Sleeping 0.15s for port stabilization...")
                time.sleep(0.15)

                # Check buffer states after stabilization
                logger.debug(f"[DEBUG] After stabilization - in_waiting: {self._serial.in_waiting}, out_waiting: {self._serial.out_waiting}")

                self._connected = True
                logger.info(f"[SUCCESS] Connected to robot on {self._port}")

        except ImportError as e:
            logger.warning(f"[WARNING] PySerial not installed, using mock mode. Error: {e}")
            logger.debug(f"[DEBUG] ImportError traceback:\n{traceback.format_exc()}")
            self._connected = False
        except Exception as e:
            logger.error(f"[ERROR] Failed to connect to robot: {e}")
            logger.debug(f"[DEBUG] Connection error traceback:\n{traceback.format_exc()}")
            self._connected = False
            raise SerialNotConnectedError(f"Cannot connect to {self._port}: {e}")

    def close(self) -> None:
        """Close the serial port gracefully."""
        logger.debug(f"[DEBUG] close() called")
        with self._lock:
            if self._serial and self._serial.is_open:
                logger.debug(f"[DEBUG] Closing serial port...")
                try:
                    self._serial.close()
                    logger.debug(f"[DEBUG] Serial port closed successfully")
                except Exception as e:
                    logger.error(f"[ERROR] Error closing serial port: {e}")
                    logger.debug(f"[DEBUG] Close error traceback:\n{traceback.format_exc()}")
            else:
                logger.debug(f"[DEBUG] Serial was already closed or None")
            self._serial = None
            self._connected = False
            logger.info("[INFO] Disconnected from robot")

    def is_connected(self) -> bool:
        """Return True if serial port is open."""
        connected = self._connected and self._serial is not None and self._serial.is_open
        logger.debug(f"[DEBUG] is_connected() check: _connected={self._connected}, _serial={self._serial is not None}, is_open={self._serial.is_open if self._serial else 'N/A'} => {connected}")
        return connected

    def _require_serial(self):
        logger.debug(f"[DEBUG] _require_serial() called")
        if not self.is_connected():
            logger.error(f"[ERROR] Serial port not connected when required!")
            raise SerialNotConnectedError("Serial port not connected")
        logger.debug(f"[DEBUG] Serial connection verified OK")

    def _validate_job(self, dose_g: float, grind_grade: int, doser_no: int, recipe_no: int) -> None:
        if not (self._MIN_DOSE <= dose_g <= self._MAX_DOSE):
            raise ValueError(f"dose_g must be {self._MIN_DOSE}–{self._MAX_DOSE}")
        if not (self._MIN_GRADE <= grind_grade <= self._MAX_GRADE):
            raise ValueError(f"grind_grade must be {self._MIN_GRADE}–{self._MAX_GRADE}")
        if not (self._MIN_DOSER <= doser_no <= self._MAX_DOSER):
            raise ValueError(f"doser_no must be {self._MIN_DOSER}–{self._MAX_DOSER}")
        if not (self._MIN_RECIPE <= recipe_no <= self._MAX_RECIPE):
            raise ValueError(f"recipe_no must be {self._MIN_RECIPE}–{self._MAX_RECIPE}")

    def _format_job_line(self, cmd: JobCommand) -> bytes:
        line = f"JOB,{cmd.dose_g},{cmd.grind_grade},{cmd.doser_no},{cmd.recipe_no}"
        return line.encode("ascii") + self._newline

    def _read_response(self, timeout: float = None) -> Optional[bytes]:
        """
        Read response from serial using the same approach as the working test script.
        Waits for data to arrive, then reads all available bytes.
        """
        if timeout is None:
            timeout = self._ack_timeout

        logger.debug(f"[DEBUG] _read_response() called, timeout={timeout}s")
        start_time = time.monotonic()
        accumulated_data = b""

        # Poll for incoming data frequently instead of sleeping a single long interval.
        # This helps catch immediate responses and allows faster reaction if data arrives quickly.
        poll_deadline = time.monotonic() + 0.5  # short initial window to allow device to start sending
        while time.monotonic() < poll_deadline:
            if self._serial.in_waiting > 0:
                break
            time.sleep(0.02)

        while (time.monotonic() - start_time) < timeout:
            try:
                # Check serial state before read
                if not self._serial or not self._serial.is_open:
                    logger.error(f"[ERROR] Serial port closed during read!")
                    return None

                # Check bytes waiting (like working script: ser.in_waiting)
                in_waiting = self._serial.in_waiting
                logger.debug(f"[DEBUG] in_waiting={in_waiting}, accumulated={len(accumulated_data)} bytes")

                if in_waiting > 0:
                    # Read all available bytes (like working script: ser.read(ser.in_waiting))
                    data = self._serial.read(in_waiting)
                    logger.debug(f"[DEBUG] Read {len(data)} bytes: {data!r}")
                    logger.debug(f"[DEBUG] Hex: {data.hex()}")
                    accumulated_data += data

                    # Check if we have a complete response (ends with newline or contains ACK/ERR)
                    decoded = accumulated_data.decode('ascii', errors='replace').strip()
                    if decoded:
                        # Check for complete response
                        if decoded.upper() in ('ACK', 'OK') or decoded.upper().startswith('ERR'):
                            logger.debug(f"[DEBUG] Complete response detected: {decoded}")
                            return accumulated_data.strip()
                        # Also check if we got a newline (complete line)
                        if b'\n' in accumulated_data or b'\r' in accumulated_data:
                            logger.debug(f"[DEBUG] Newline detected, response complete")
                            return accumulated_data.strip()

                    # Small delay before checking for more data
                    time.sleep(0.1)
                else:
                    # No bytes available now — try a short non-blocking readline as a fallback
                    try:
                        original_timeout = getattr(self._serial, 'timeout', None)
                        # Use a short temporary timeout so we don't block long here
                        self._serial.timeout = min(0.5, self._read_timeout)
                        line = self._serial.readline()
                        if line:
                            logger.debug(f"[DEBUG] readline got {len(line)} bytes: {line!r}")
                            accumulated_data += line
                            decoded = accumulated_data.decode('ascii', errors='replace').strip()
                            if decoded.upper() in ('ACK', 'OK') or decoded.upper().startswith('ERR') or b'\n' in accumulated_data or b'\r' in accumulated_data:
                                logger.debug(f"[DEBUG] Line read detected complete response: {decoded}")
                                return accumulated_data.strip()
                    except Exception as e:
                        logger.debug(f"[DEBUG] Short readline failed or returned nothing: {e}")
                    finally:
                        # Restore original timeout if possible
                        try:
                            self._serial.timeout = original_timeout
                        except Exception:
                            pass

                    # Check if we already have a complete response
                    if accumulated_data:
                        decoded = accumulated_data.decode('ascii', errors='replace').strip()
                        if decoded.upper() in ('ACK', 'OK') or decoded.upper().startswith('ERR'):
                            logger.debug(f"[DEBUG] Returning accumulated response: {decoded}")
                            return accumulated_data.strip()

                    time.sleep(0.05)

            except Exception as e:
                logger.error(f"[ERROR] Exception during read: {e}")
                logger.debug(f"[DEBUG] Read exception traceback:\n{traceback.format_exc()}")
                if "Broken pipe" in str(e) or "disconnected" in str(e).lower():
                    logger.error(f"[ERROR] BROKEN PIPE DETECTED!")
                    self._connected = False
                return None

        # Timeout reached - return whatever we have
        if accumulated_data:
            logger.warning(f"[WARNING] Timeout, returning partial data: {accumulated_data!r}")
            return accumulated_data.strip()

        logger.warning(f"[WARNING] Timeout reached, no data received")
        return None

    def send_job(self, dose_g: int, grind_grade: int, doser_no: int, recipe_no: int, wait_for_ack: bool = False) -> str:
        """
        Send a drink job to the robot board.

        By default this method is non-blocking with respect to serial
        acknowledgements: it sends the JOB line and returns immediately with
        'SENT'. If `wait_for_ack` is True the previous blocking behaviour is
        retained (waits for 'ACK', 'OK' or 'ERR...' and returns that value).
        """
        logger.debug(f"[DEBUG] send_job() called: dose_g={dose_g}, grind_grade={grind_grade}, doser_no={doser_no}, recipe_no={recipe_no}")

        self._validate_job(dose_g, grind_grade, doser_no, recipe_no)
        logger.debug(f"[DEBUG] Job parameters validated OK")

        cmd = JobCommand(dose_g, grind_grade, doser_no, recipe_no)
        logger.debug(f"[DEBUG] JobCommand created: {cmd}")

        with self._lock:
            logger.debug(f"[DEBUG] Lock acquired for send_job")

            self._require_serial()

            # Check serial health before write
            logger.debug(f"[DEBUG] Pre-write serial state:")
            logger.debug(f"[DEBUG]   is_open: {self._serial.is_open}")
            logger.debug(f"[DEBUG]   in_waiting: {self._serial.in_waiting}")
            logger.debug(f"[DEBUG]   out_waiting: {self._serial.out_waiting}")

            # Clear any stale data in buffers
            if self._serial.in_waiting > 0:
                stale_data = self._serial.read(self._serial.in_waiting)
                logger.warning(f"[WARNING] Cleared {len(stale_data)} stale bytes from input buffer: {stale_data!r}")

            tx_line = self._format_job_line(cmd)
            logger.debug(f"[DEBUG] Formatted TX line: {tx_line!r}")
            logger.debug(f"[DEBUG] TX line hex: {tx_line.hex()}")

            try:
                bytes_written = self._serial.write(tx_line)
                logger.info(f"[INFO] Sent: {tx_line.decode().strip()} ({bytes_written} bytes)")
                logger.debug(f"[DEBUG] Write completed, bytes_written={bytes_written}")

                logger.debug(f"[DEBUG] Flushing serial output...")
                self._serial.flush()
                logger.debug(f"[DEBUG] Flush completed")

                # Verify out_waiting after flush
                logger.debug(f"[DEBUG] Post-flush out_waiting: {self._serial.out_waiting}")

            except Exception as e:
                logger.error(f"[ERROR] Write/flush failed: {e}")
                logger.debug(f"[DEBUG] Write error traceback:\n{traceback.format_exc()}")
                if "Broken pipe" in str(e) or "write" in str(e).lower():
                    logger.error(f"[ERROR] BROKEN PIPE on write - marking connection as dead")
                    self._connected = False
                raise SerialProtocolError(f"Write failed: {e}")
            # If the caller doesn't want to wait for an acknowledgement,
            # return immediately after the write/flush. This makes the send
            # non-blocking with respect to serial ACKs.
            if not wait_for_ack:
                logger.info("[INFO] Job sent (non-blocking mode) - not waiting for ACK")
                return "SENT"

            logger.debug(f"[DEBUG] Waiting for response, timeout={self._ack_timeout}s")

            response = self._read_response(timeout=self._ack_timeout)

            if response is None:
                logger.error(f"[ERROR] No response received within {self._ack_timeout}s timeout")
                # Try to diagnose the issue
                logger.debug(f"[DEBUG] Post-timeout serial state:")
                try:
                    logger.debug(f"[DEBUG]   is_open: {self._serial.is_open}")
                    logger.debug(f"[DEBUG]   in_waiting: {self._serial.in_waiting}")
                except Exception as e:
                    logger.error(f"[ERROR] Cannot check serial state: {e}")
                raise SerialProtocolError("Timeout waiting for ACK/ERR")

            response_str = response.decode("ascii", errors="replace")
            logger.info(f"[INFO] Received: {response_str}")
            logger.debug(f"[DEBUG] Response bytes: {response!r}")

            if response_str.upper() == "ACK":
                logger.debug(f"[DEBUG] ACK received successfully")
                return "ACK"
            elif response_str.upper() in ("OK", "DONE", "COMPLETE"):
                # Robot might send completion directly without separate ACK
                logger.debug(f"[DEBUG] Completion received: {response_str}")
                return response_str.upper()
            elif response_str.upper().startswith("ERR"):
                logger.error(f"[ERROR] Robot returned error: {response_str}")
                raise SerialProtocolError(f"Robot error: {response_str}")
            else:
                logger.warning(f"[WARNING] Unexpected response format: {response_str}")
                raise SerialProtocolError(f"Unexpected response: {response_str}")

    def wait_for_completion(self, timeout: float = 60.0) -> str:
        """
        Wait for job completion notification from robot.
        Call this after send_job returns ACK.
        Returns completion message (OK, DONE, COMPLETE) or raises timeout.
        """
        logger.debug(f"[DEBUG] wait_for_completion() called, timeout={timeout}s")

        with self._lock:
            self._require_serial()

            logger.debug(f"[DEBUG] Waiting for completion notification...")
            response = self._read_response(timeout=timeout)

            if response is None:
                logger.warning(f"[WARNING] No completion notification within {timeout}s")
                raise SerialProtocolError("Timeout waiting for completion")

            response_str = response.decode("ascii", errors="replace").strip()
            logger.info(f"[INFO] Completion notification: {response_str}")

            if response_str.upper() in ("OK", "DONE", "COMPLETE", "FINISHED"):
                return response_str.upper()
            elif response_str.upper().startswith("ERR"):
                raise SerialProtocolError(f"Robot error during job: {response_str}")
            else:
                # Accept any response as potential completion
                logger.warning(f"[WARNING] Unexpected completion format: {response_str}")
                return response_str

    def get_status(self) -> str:
        """Request status from the robot."""
        logger.debug(f"[DEBUG] get_status() called")

        with self._lock:
            logger.debug(f"[DEBUG] Lock acquired for get_status")

            self._require_serial()

            # Check serial health before operation
            logger.debug(f"[DEBUG] Pre-status serial state:")
            logger.debug(f"[DEBUG]   is_open: {self._serial.is_open}")
            logger.debug(f"[DEBUG]   in_waiting: {self._serial.in_waiting}")
            logger.debug(f"[DEBUG]   out_waiting: {self._serial.out_waiting}")

            # Clear any stale data
            if self._serial.in_waiting > 0:
                stale_data = self._serial.read(self._serial.in_waiting)
                logger.warning(f"[WARNING] Cleared {len(stale_data)} stale bytes: {stale_data!r}")

            status_cmd = b"STATUS" + self._newline
            logger.debug(f"[DEBUG] Sending status command: {status_cmd!r}")

            try:
                bytes_written = self._serial.write(status_cmd)
                logger.debug(f"[DEBUG] Status command sent ({bytes_written} bytes)")

                # Flush BEFORE reading (was incorrectly placed after)
                logger.debug(f"[DEBUG] Flushing serial output...")
                self._serial.flush()
                logger.debug(f"[DEBUG] Flush completed")

            except Exception as e:
                logger.error(f"[ERROR] Failed to send STATUS command: {e}")
                logger.debug(f"[DEBUG] Status write error traceback:\n{traceback.format_exc()}")
                if "Broken pipe" in str(e):
                    logger.error(f"[ERROR] BROKEN PIPE on status write")
                    self._connected = False
                raise SerialProtocolError(f"Status write failed: {e}")

            logger.debug(f"[DEBUG] Waiting for status response, timeout={self._ack_timeout}s")

            response = self._read_response(timeout=self._ack_timeout)

            if response:
                response_str = response.decode("ascii", errors="replace")
                logger.info(f"[INFO] Status response: {response_str}")
                return response_str

            logger.error(f"[ERROR] No status response received")
            raise SerialProtocolError("Timeout waiting for status response")


    def send_check(self) -> str:
        """
        Send a CHECK command to query delivery cup and coffee server presence.
        Returns the raw response string (e.g. "data,1,0,0,1,0").
        """
        logger.debug("[DEBUG] send_check() called")

        with self._lock:
            self._require_serial()

            # Clear stale data
            if self._serial.in_waiting > 0:
                stale_data = self._serial.read(self._serial.in_waiting)
                logger.warning(f"[WARNING] Cleared {len(stale_data)} stale bytes: {stale_data!r}")

            check_cmd = b"CHECK" + self._newline
            logger.debug(f"[DEBUG] Sending check command: {check_cmd!r}")

            try:
                bytes_written = self._serial.write(check_cmd)
                logger.debug(f"[DEBUG] Check command sent ({bytes_written} bytes)")
                self._serial.flush()
            except Exception as e:
                logger.error(f"[ERROR] Failed to send CHECK command: {e}")
                if "Broken pipe" in str(e):
                    self._connected = False
                raise SerialProtocolError(f"CHECK write failed: {e}")

            response = self._read_response(timeout=self._ack_timeout)

            if response is None:
                raise SerialProtocolError("Timeout waiting for CHECK response")

            response_str = response.decode("ascii", errors="replace").strip()
            logger.info(f"[INFO] CHECK response: {response_str}")
            return response_str

    def check_connection_health(self) -> tuple[bool, str]:
        """
        Check if the serial connection is healthy.
        Returns (is_healthy: bool, status_message: str)
        """
        logger.debug(f"[DEBUG] check_connection_health() called")

        if self._serial is None:
            logger.debug(f"[DEBUG] Health check: _serial is None")
            return False, "Serial object is None"

        if not self._serial.is_open:
            logger.debug(f"[DEBUG] Health check: Serial port not open")
            return False, "Serial port is not open"

        try:
            # Check if we can access port properties (will fail on broken pipe)
            in_waiting = self._serial.in_waiting
            out_waiting = self._serial.out_waiting
            logger.debug(f"[DEBUG] Health check OK: in_waiting={in_waiting}, out_waiting={out_waiting}")
            return True, f"Healthy (in_waiting={in_waiting}, out_waiting={out_waiting})"
        except OSError as e:
            logger.error(f"[ERROR] Health check failed with OSError: {e}")
            self._connected = False
            return False, f"OSError: {e}"
        except Exception as e:
            logger.error(f"[ERROR] Health check failed: {e}")
            return False, f"Error: {e}"

    def reconnect(self, max_attempts: int = 3, delay: float = 1.0) -> bool:
        """
        Attempt to reconnect to the serial port.
        Returns True if reconnection successful.
        """
        logger.info(f"[INFO] Attempting reconnection (max {max_attempts} attempts)...")

        for attempt in range(1, max_attempts + 1):
            logger.debug(f"[DEBUG] Reconnect attempt {attempt}/{max_attempts}")

            # First, close existing connection
            self.close()
            time.sleep(delay)

            try:
                self.connect()
                if self.is_connected():
                    logger.info(f"[SUCCESS] Reconnected on attempt {attempt}")
                    return True
            except Exception as e:
                logger.warning(f"[WARNING] Reconnect attempt {attempt} failed: {e}")

            time.sleep(delay)

        logger.error(f"[ERROR] Failed to reconnect after {max_attempts} attempts")
        return False


# Global singleton instance
_robot_client: Optional[RobotControlBoardSerialClient] = None
_robot_lock = threading.Lock()


def is_demo_mode() -> bool:
    """Check if running in demo mode (no physical robot)."""
    from django.conf import settings
    return getattr(settings, 'ROBOT_DEMO_MODE', False)


def get_robot_client() -> RobotControlBoardSerialClient:
    """Get or create the global robot client instance."""
    global _robot_client
    with _robot_lock:
        if _robot_client is None:
            from django.conf import settings
            port = getattr(settings, 'ROBOT_SERIAL_PORT', 'COM6')
            baudrate = getattr(settings, 'ROBOT_BAUDRATE', 115200)
            _robot_client = RobotControlBoardSerialClient(port=port, baudrate=baudrate)
        return _robot_client


def send_manual_order(dose_g: int, grind_grade: int, doser_no: int, recipe_no: int) -> tuple[bool, str]:
    """
    Send a manual order to the robot.
    Returns (success: bool, message: str)
    """
    logger.debug(f"[DEBUG] send_manual_order() called: dose={dose_g}g, grade={grind_grade}, doser={doser_no}, recipe={recipe_no}")

    # Demo mode - simulate successful order
    if is_demo_mode():
        logger.info(f"[DEMO] Simulating order: {dose_g}g, grade {grind_grade}, doser {doser_no}, recipe {recipe_no}")
        time.sleep(0.5)  # Simulate processing time
        return True, "ACK (Demo Mode)"

    client = get_robot_client()

    # Check connection health first
    is_healthy, health_status = client.check_connection_health()
    logger.debug(f"[DEBUG] Connection health: {is_healthy}, status: {health_status}")

    if not is_healthy:
        logger.warning(f"[WARNING] Connection unhealthy, attempting reconnect...")
        if not client.reconnect():
            return False, f"Robot connection lost and reconnect failed: {health_status}"

    # Check if connected, try to connect if not
    if not client.is_connected():
        logger.debug(f"[DEBUG] Not connected, attempting to connect...")
        try:
            client.connect()
        except SerialNotConnectedError as e:
            logger.error(f"[ERROR] Failed to connect: {e}")
            return False, f"Robot not connected: {e}"

    try:
        # Perform pre-use check FIRST to verify delivery cup and coffee servers are available
        logger.info("[INFO] Performing pre-use check (CHECK command)...")
        pre = check_pre_use()
        if not pre.get("ok"):
            logger.error(f"[ERROR] Pre-use check failed: {pre.get('message')}")
            return False, f"Pre-use check failed: {pre.get('message')}"

        logger.info("[INFO] Pre-use check passed, cup and servers verified")

        # Select first available server
        servers = pre.get("servers", [False, False, False, False])
        server_no = None
        for idx, available in enumerate(servers, start=1):
            if available:
                server_no = idx
                break

        if server_no is None:
            logger.error("[ERROR] No coffee server available")
            return False, "No coffee server available"

        logger.info(f"[INFO] Selected coffee server S{server_no}")

        # Now send JOB command to robot after CHECK succeeds
        logger.debug(f"[DEBUG] Sending JOB command to robot...")
        result = client.send_job(dose_g, grind_grade, doser_no, recipe_no)
        logger.info(f"[SUCCESS] JOB command sent successfully (serial): {result}")

        # Now send commands to the cobot over Ethernet socket
        logger.info("[INFO] Sending the robot commands over ethernet socket")
        ok, msg = send_tcp_command_to_cobot(doser_no, recipe_no, server_no, grind_grade)
        if ok:
            logger.info(f"[SUCCESS] Order finished: {msg}")
            return True, msg
        else:
            logger.error(f"[ERROR] Ethernet command failed: {msg}")
            return False, f"Ethernet command failed: {msg}"
    except SerialProtocolError as e:
        logger.error(f"[ERROR] Protocol error: {e}")
        # Check if it's a broken pipe and try reconnect
        if "Broken pipe" in str(e) or "Write failed" in str(e):
            logger.warning(f"[WARNING] Broken pipe detected, will try reconnect on next call")
        return False, str(e)
    except SerialNotConnectedError as e:
        logger.error(f"[ERROR] Not connected: {e}")
        return False, str(e)
    except Exception as e:
        logger.exception("[ERROR] Unexpected error sending order")
        logger.debug(f"[DEBUG] Full traceback:\n{traceback.format_exc()}")
        return False, f"Unexpected error: {e}"


def wait_for_order_completion(timeout: float = 60.0) -> tuple[bool, str]:
    """
    Wait for robot to send completion notification.
    Call this after send_manual_order returns successfully.
    Returns (success: bool, message: str)
    """
    logger.debug(f"[DEBUG] wait_for_order_completion() called, timeout={timeout}s")

    # Demo mode - simulate completion
    if is_demo_mode():
        logger.info(f"[DEMO] Simulating completion after 2 seconds")
        time.sleep(2.0)
        return True, "DONE (Demo Mode)"

    client = get_robot_client()

    if not client.is_connected():
        return False, "Robot not connected"

    try:
        result = client.wait_for_completion(timeout=timeout)
        logger.info(f"[SUCCESS] Order completed: {result}")
        return True, result
    except SerialProtocolError as e:
        logger.error(f"[ERROR] Completion error: {e}")
        return False, str(e)
    except Exception as e:
        logger.exception("[ERROR] Unexpected error waiting for completion")
        return False, f"Unexpected error: {e}"


def send_tcp_command_to_cobot(doser_no: int, recipe_no: int, server_no: int, grinder_no: int, host: str = "192.168.57.10", port: int = 1233, connect_timeout: float = 10.0, response_timeout: float = 30.0) -> tuple[bool, str]:
    """
    Act as a TCP server for the cobot client.

    Workflow expected by the cobot (client) pseudocode provided by the user:
    - The cobot will open a connection to (host, port), then send "OK" as a handshake.
    - The server (this function) should respond with "start" and then send the command parameters.
    - The cobot performs tasks and then sends back "Done" (or similar).

    Note: server_no MUST be pre-determined by the caller by calling check_pre_use()
    to avoid redundant CHECK commands being sent to the robot.

    Args:
        doser_no: Doser number (1-4)
        recipe_no: Recipe number (1-4)
        server_no: Coffee server number (1-4), must be pre-determined by caller
        grinder_no: Grinder number (1-2) used to choose G1 or G2 (must be provided by caller)
        host: TCP server host
        port: TCP server port
        connect_timeout: Timeout for cobot client connection
        response_timeout: Timeout for command responses

    Returns (True, message) on success where message is the response from the cobot (e.g. "Done").
    Returns (False, error_message) on failure.
    """

    logger.debug(f"[DEBUG] send_tcp_command_to_cobot() called: doser={doser_no}, recipe={recipe_no}, server_no={server_no}, grinder_no={grinder_no}, host={host}, port={port}")

    # Simple validation
    try:
        doser_no = int(doser_no)
        recipe_no = int(recipe_no)
        server_no = int(server_no)
        grinder_no = int(grinder_no)
    except Exception:
        return False, "Invalid doser_no, recipe_no, server_no, or grinder_no (must be integers)"

    # Validate server_no
    if not (1 <= server_no <= 4):
        return False, "server_no must be 1..4"

    # Validate grinder_no (caller is expected to pass 1 or 2)
    if grinder_no not in (1, 2):
        logger.warning(f"[WARNING] Invalid grinder_no {grinder_no} received; expected 1 or 2. Defaulting to 1")
        grinder_no = 1
    logger.info(f"[INFO] Using grinder G{grinder_no} (from parameter)")

    # Create listening socket and wait for client to connect
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((host, port))
        except OSError as e:
            logger.error(f"[ERROR] Failed to bind to {host}:{port}: {e}")
            return False, f"Bind failed: {e}"
        srv.listen(1)
        srv.settimeout(connect_timeout)
        logger.info(f"[INFO] TCP server listening on {host}:{port}, waiting for cobot client connection...")

        try:
            conn, addr = srv.accept()
        except socket.timeout:
            return False, f"Timeout waiting for cobot client to connect on {host}:{port}"

        with closing(conn):
            logger.info(f"[INFO] Cobot client connected from {addr}")
            conn.settimeout(1.0)

            # Initial handshake from client (expecting "OK" or similar)
            try:
                data = conn.recv(1024)
                if not data:
                    return False, "No handshake data received from client"
                recv = data.decode('utf-8', errors='replace').strip()
                logger.debug(f"[DEBUG] Handshake received: {recv}")
                logger.info(f"[INFO] Handshake raw bytes: {data!r} hex:{data.hex()} decoded:{recv}")
                print(f"Handshake raw: {data!r} hex:{data.hex()} decoded: {recv}")
            except socket.timeout:
                return False, "Timeout while waiting for client handshake"
            except Exception as e:
                logger.error(f"[ERROR] Error reading handshake: {e}")
                return False, f"Handshake read error: {e}"

            # Send "start" and expect an ACK from the client
            try:
                conn.sendall(b"start")
                logger.info("[INFO] Sent: start")
            except Exception as e:
                logger.error(f"[ERROR] Failed to send 'start': {e}")
                return False, f"Send error: {e}"

            # Wait for ACK from client
            deadline = time.time() + response_timeout
            ack_received = False
            buffer = b""
            while time.time() < deadline:
                try:
                    chunk = conn.recv(1024)
                    if not chunk:
                        time.sleep(0.05)
                        continue
                    buffer += chunk
                    text = buffer.decode('utf-8', errors='replace').strip()
                    logger.debug(f"[DEBUG] Waiting for ACK, received chunk: {text}")
                    logger.info(f"[INFO] ACK wait - chunk raw: {chunk!r} hex:{chunk.hex()} buffer raw: {buffer!r} buffer_hex:{buffer.hex()} decoded:{text}")
                    print(f"ACK wait recv chunk: {chunk!r} hex:{chunk.hex()} buffer: {buffer!r}")
                    if text.lower() in ("ack", "ok"):
                        ack_received = True
                        logger.info(f"[INFO] ACK received from client: {text}")
                        break
                    # otherwise keep collecting until timeout
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"[ERROR] Error while waiting for ACK: {e}")
                    return False, f"Receive error: {e}"

            if not ack_received:
                logger.warning("[WARNING] ACK not received after start")
                return False, "ACK not received from client after start"

            # Sequence: GO_TO_D -> GO_TO_Gn -> GO_TO_S -> RETURN_TO_D -> RETURN_TO_S -> GO_TO_R
            def _send_and_wait(msg: str, step_name: str) -> tuple[bool, str]:
                """Helper to send a message and wait for Done/OK response."""
                try:
                    payload = msg.encode('utf-8')
                    logger.info(f"[INFO] Sent: {msg}")
                    logger.debug(f"[DEBUG] Sending payload for {step_name}: {payload!r} hex:{payload.hex()}")
                    print(f"Sending: {payload!r}")
                    conn.sendall(payload)
                except Exception as e:
                    logger.error(f"[ERROR] Failed to send {step_name}: {e}")
                    return False, f"Send error: {e}"

                deadline = time.time() + response_timeout
                buffer = b""
                while time.time() < deadline:
                    try:
                        chunk = conn.recv(1024)
                        if not chunk:
                            time.sleep(0.05)
                            continue
                        buffer += chunk
                        text = buffer.decode('utf-8', errors='replace').strip()
                        logger.debug(f"[DEBUG] Waiting for {step_name} Done, received: {text}")
                        logger.info(f"[INFO] {step_name} recv chunk raw: {chunk!r} hex:{chunk.hex()} buffer raw: {buffer!r} buffer_hex:{buffer.hex()} decoded:{text}")
                        print(f"{step_name} recv: {chunk!r} hex:{chunk.hex()} buffer: {buffer!r}")
                        if text.lower().startswith("done") or text.lower() in ("done", "ok"):
                            logger.info(f"[INFO] {step_name} completed: {text}")
                            return True, text
                    except socket.timeout:
                        continue
                    except Exception as e:
                        logger.error(f"[ERROR] Error while waiting for {step_name}: {e}")
                        return False, f"Receive error: {e}"

                logger.warning(f"[WARNING] Timeout waiting for {step_name} completion")
                return False, f"Timeout waiting for {step_name} completion"

            # 1) GO_TO_Dn
            ok, resp = _send_and_wait(f"GO_TO_D{doser_no}", f"GO_TO_D{doser_no}")
            if not ok:
                return False, resp

            # 2) GO_TO_Gn (dynamic grinder based on grind_grade)
            ok, resp = _send_and_wait(f"GO_TO_G{grinder_no}", f"GO_TO_G{grinder_no}")
            if not ok:
                return False, resp

            # 3) GO_TO_Sn
            ok, resp = _send_and_wait(f"GO_TO_S{server_no}", f"GO_TO_S{server_no}")
            if not ok:
                return False, resp

            # 4) RETURN_TO_Dn (only if we previously sent a GO_TO_D)
            ok, resp = _send_and_wait(f"RETURN_TO_D{doser_no}", f"RETURN_TO_D{doser_no}")
            if not ok:
                return False, resp

            # 5) RETURN_TO_Sn
            ok, resp = _send_and_wait(f"RETURN_TO_S{server_no}", f"RETURN_TO_S{server_no}")
            if not ok:
                return False, resp

            # 6) GO_TO_Rn
            ok, resp = _send_and_wait(f"GO_TO_R{recipe_no}", f"GO_TO_R{recipe_no}")
            if not ok:
                return False, resp

            # All steps succeeded
            return True, resp

    except Exception as e:
        logger.error(f"[ERROR] TCP server error: {e}")
        logger.debug(f"[DEBUG] TCP server traceback:\n{traceback.format_exc()}")
        return False, str(e)
    finally:
        try:
            srv.close()
        except Exception:
            pass


def check_robot_connection() -> tuple[bool, str]:
    """
    Check if robot is connected.
    Note: We only check if the serial port is open, not if the robot responds to STATUS.
    The robot may not support STATUS command - it only responds to JOB commands.
    """
    logger.debug(f"[DEBUG] check_robot_connection() called")

    # Demo mode - always connected
    if is_demo_mode():
        logger.debug(f"[DEBUG] Demo mode active")
        return True, "Demo Mode - Simulated Connection"

    client = get_robot_client()

    # Check connection health first
    is_healthy, health_status = client.check_connection_health()
    logger.debug(f"[DEBUG] Health check result: healthy={is_healthy}, status={health_status}")

    if not is_healthy:
        logger.warning(f"[WARNING] Unhealthy connection detected: {health_status}")
        # Try to reconnect
        if client.reconnect():
            logger.info(f"[INFO] Reconnected successfully after health check failure")
        else:
            logger.error(f"[ERROR] Reconnect failed after health check failure")
            return False, f"Connection unhealthy: {health_status}"

    if not client.is_connected():
        logger.debug(f"[DEBUG] Not connected, attempting connection...")
        try:
            client.connect()
            logger.info(f"[INFO] Connected successfully")
        except SerialNotConnectedError as e:
            logger.error(f"[ERROR] Failed to connect: {e}")
            return False, f"Failed to connect: {e}"

    # If we got here, serial port is open and healthy
    if client.is_connected():
        logger.info(f"[INFO] Robot connected on {client._port}")
        return True, f"Connected on {client._port}"

    return False, "Unknown connection state"


def check_pre_use() -> dict:
    """
    Send a CHECK command to verify the delivery cup and coffee servers
    are present before allowing an order.

    Returns a dict:
        ok (bool): True if cup is present AND at least one server is present.
        cup_present (bool): Whether the delivery cup is detected.
        servers (list[bool]): Presence of the four coffee servers.
        message (str): Human-readable summary.
    """
    logger.debug("[DEBUG] check_pre_use() called")

    # Demo mode — simulate everything present
    if is_demo_mode():
        logger.info("[DEMO] Simulating pre-use check: all present")
        return {
            "ok": True,
            "cup_present": True,
            "servers": [True, True, True, True],
            "message": "All present (Demo Mode)",
        }

    client = get_robot_client()

    # Ensure connection (same pattern as send_manual_order)
    is_healthy, health_status = client.check_connection_health()
    if not is_healthy:
        logger.warning(f"[WARNING] Connection unhealthy for CHECK, attempting reconnect...")
        if not client.reconnect():
            return {
                "ok": False,
                "cup_present": False,
                "servers": [False, False, False, False],
                "message": f"Robot connection lost: {health_status}",
            }

    if not client.is_connected():
        try:
            client.connect()
        except SerialNotConnectedError as e:
            return {
                "ok": False,
                "cup_present": False,
                "servers": [False, False, False, False],
                "message": f"Robot not connected: {e}",
            }

    # Send the CHECK command
    try:
        raw = client.send_check()
    except (SerialProtocolError, SerialNotConnectedError) as e:
        logger.error(f"[ERROR] CHECK command failed: {e}")
        return {
            "ok": False,
            "cup_present": False,
            "servers": [False, False, False, False],
            "message": f"CHECK command failed: {e}",
        }

    # Parse response: expected format "data,<cup>,<s1>,<s2>,<s3>,<s4>"
    try:
        parts = raw.split(",")
        if len(parts) < 6 or parts[0].strip().lower() != "data":
            raise ValueError(f"Unexpected CHECK response format: {raw}")

        values = [int(v.strip()) for v in parts[1:6]]
        cup_present = values[0] == 1
        servers = [v == 1 for v in values[1:5]]
    except (ValueError, IndexError) as e:
        logger.error(f"[ERROR] Failed to parse CHECK response '{raw}': {e}")
        return {
            "ok": False,
            "cup_present": False,
            "servers": [False, False, False, False],
            "message": f"Invalid CHECK response: {raw}",
        }

    any_server = any(servers)
    ok = cup_present and any_server

    # Build human-readable message
    if ok:
        message = "Pre-use check passed"
    else:
        problems = []
        if not cup_present:
            problems.append("Delivery cup is missing")
        if not any_server:
            problems.append("No coffee server detected")
        message = ". ".join(problems)

    logger.info(f"[INFO] Pre-use check: ok={ok}, cup={cup_present}, servers={servers}")
    return {
        "ok": ok,
        "cup_present": cup_present,
        "servers": servers,
        "message": message,
    }


# TCP server functionality removed — using per-call server in `send_tcp_command_to_cobot` (original behavior)
