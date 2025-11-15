import serial

class SerialLink:
    """Simple wrapper for pyserial to communicate with the robot arm."""
    def __init__(self, port: str, baudrate: int = 115200) -> None:
        self.port = port
        self.baudrate = baudrate
        self.ser = serial.Serial(port, baudrate=baudrate, timeout=1)

    def send_command(self, command: str) -> None:
        """Send a single command string terminated with newline."""
        if not command:
            return
        self.ser.write((command + "\n").encode("utf-8"))

    def close(self) -> None:
        """Close the serial connection."""
        if self.ser.is_open:
            self.ser.close()
