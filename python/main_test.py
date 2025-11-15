from serial_link import SerialLink

def main() -> None:
    """Simple test program for the SerialLink class."""
    # Change '/dev/ttyUSB0' to the appropriate serial port on your system.
    link = SerialLink('/dev/ttyUSB0', 115200)
    try:
        link.send_command('M279')
        link.send_command('M400')
    finally:
        link.close()


if __name__ == "__main__":
    main()
