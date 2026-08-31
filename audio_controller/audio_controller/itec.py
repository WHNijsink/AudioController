""" Communicate with the ITEC device, to

 - measure the sound level on IN ports
 - control the route of audio (from IN to OUT ports)

See for more info the ITEC manuals at https://www.itec-audio.com/downloads/anleitungen/

"""
# standard lib
import sys, os, time
import datetime as dt
import re
from typing import List
import logging
import traceback

# external
import serial

# internal
from . import settings

_last_time_get_serial = None

main_logger = logging.getLogger("main")


def _filter_usb_ports(names):
    """Return the ttyUSB* device names from a /dev listing (S6: no shell)."""
    return sorted(n for n in names if n.startswith("ttyUSB") and n != "ttyUSB")


def get_usb_port():
    try:
        ports = _filter_usb_ports(os.listdir("/dev"))
    except OSError:
        ports = []
    msg = f"Found {len(ports)} serial usb connections: {ports}"
    print(msg)
    main_logger.info(msg)
    if not ports:
        return "/dev/ttyUSB0"
    return f"/dev/{ports[0]}"


def get_serial():
    """ seriele poort confguratie """
    # only try to open the port every ... seconds
    retry_time = 5  # seconds
    global _last_time_get_serial
    if _last_time_get_serial is not None and _last_time_get_serial > dt.datetime.utcnow() - dt.timedelta(seconds=retry_time):
        return None

    _last_time_get_serial = dt.datetime.utcnow()

    port = get_usb_port()
    result = serial.Serial()
    # see manual Software Multimix
    result.baudrate = 19200
    result.bytesize = serial.EIGHTBITS
    result.parity = serial.PARITY_NONE
    result.stopbits = serial.STOPBITS_ONE
    result.port = port
    result.timeout = 0.05  # seconds
    result.write_timeout = 0.05  # seconds
    try:
        result.open()
    except:
        msg = f"Cannot open serial port. Do you have permissions on {port}?"
        # possible solution: sudo chmod 666 /dev/ttyUSB0
        print(msg)
        main_logger.info(msg)
        result = None
    return result


class ITEC():
    """ Object to communicate with ITEC switch """

    def __init__(self):
        self.device_id = 0x01  # 1..63 = 0x01..0x3F
        self.serial = get_serial()

    def write_read(self, command, r_value, value):
        """
        Write command and read result. Return result on success. Try once again if returned value is bad.
        Drop connection on exceptions, which may be recovered next call.
        """
        # try to create port again
        if self.serial is None:
            self.serial = get_serial()
            if self.serial is None:
                return None
        CR = 0x0D  # end of packet
        packet = [self.device_id, command, r_value, value, CR]
        ACK = 0x06  # device acknowledge

        def ack(result):
            return bool(result) and result[0] == self.device_id and result[1] == command and result[2] == r_value and result[4] == ACK

        try:
            self.serial.write(packet)
            result = self.serial.read(5)
            if ack(result):
                return result[3]
            else:  # try once again if not succesful (happens rarely)
                msg = "Trying again to send command to serial port"
                print(msg)
                main_logger.warning(msg)
                self.serial.write(packet)
                result = self.serial.read(5)
                if ack(result):
                    return result[3]
        except:
            # something bad happened with the connection, do not try to recover here, but maybe next call
            msg = f"Exception while writing command to serial port. Try to recover next call. Exception: \n{traceback.format_exc()}"
            print(msg)
            main_logger.error(msg)
            self.serial = None
            return None
        msg = "Failed to send command to serial port"
        print(msg)
        main_logger.warning(msg)
        return None

    def r_val_input(self, channel: int):
        """ Get the R-value (remote value) which belongs to the given input channel """
        assert 1 <= channel <= settings.settings.nr_IN_ports, f"Channel must be 1.., not {channel}"
        return 0xC0 + channel

    def set_value(self, r_value, value: int):
        """ value: 0 = mute, 255 = max """
        #assert 0 <= value <= 255, f"Value must be 0..255, not {value}"
        command = 0x80
        r = self.write_read(command, r_value, value)
        return r is not None

    def increase_value(self, r_value, delta):
        command = 0x81
        r = self.write_read(command, r_value, delta)
        return r is not None

    def decrease_value(self, r_value, delta):
        command = 0x82
        r = self.write_read(command, r_value, delta)
        return r is not None

    def mute_unmute(self, r_value, mute: bool):
        command = 0x89
        value = 0x01 if mute else 0x00
        r = self.write_read(command, r_value, value)
        return r is not None

    def get_muting_status(self, r_value):
        """ return 1 if muted, 0 if unmuted """
        command = 0x8A
        value = self.write_read(command, r_value, 0x00)
        return value

    def set_route(self, channel: int, bus: List[int]) -> bool:
        """ Set route for input channel (1..) to output bus (1..). List of bus numbers can be given.

        The following value is written to the ITEC, based on the given bus numbers:

        value  bits  meaning
        0      0000  route to nothing
        1      0001  route to bus 1 only
        2      0010  route to bus 2 only
        3      0011  route to bus 1 and 2
        4      0100  route to bus 3 only
        etc

        """
        command = 0x8B
        values: List[str] = []
        for port_nr in range(1, settings.settings.nr_OUT_ports + 1):
            values.append("1" if port_nr in bus else "0")
        value = int("".join(reversed(values)), base=2)  # int('101', base=2) == 5
        result = self.write_read(command, self.r_val_input(channel), value)
        return result is not None

    def get_route(self, channel: int) -> List[int]:
        """ Get bus numbers (output channel) which the given input channel is routed to.
        Return None if failed. Return empty list if input channel is not routed to anything.
        """
        result = []
        command = 0x8C
        value = self.write_read(command, self.r_val_input(channel), 0x00)
        if value is not None:
            values = list(reversed(format(value, 'b')))  # format(5, 'b') == '101'
            for i in range(len(values)):
                if values[i] == '1':
                    result.append(i + 1)
            return result
        return value

    def set_input_link(self, value: str):
        """ """
        command = 0x8D
        r_value = 0xC0
        # value = 0  # 0..15
        return self.write_read(command, r_value, value) is not None

    def get_input_link(self):
        """ """
        command = 0x8E
        r_value = 0xC0
        value = 0x00
        return self.write_read(command, r_value, value)

    def get_input_level(self, channel: int, prefade=True) -> float:
        """ Get input level (for input channel) in dB between -70 and 0? """
        command = 0x90 if prefade else 0x91
        value = self.write_read(command, self.r_val_input(channel), 0x00)
        if value is not None:
            level_db = value / 2 - 70
            return level_db
        return None

    def input_level_min(self):
        return -70

    def input_level_max(self):
        return 0


itec = ITEC()


def test():

    return

    # for i in [1, 2, 3, 4, 5, 6, 7, 8]:
    #    print(i, itec.set_route(i, [1, 2, 3, 4]))

    for i in [1, 2, 3, 4, 5, 6, 7, 8]:
        print(i, itec.get_route(i))

    # get_usb_port()

    sys.exit(0)
