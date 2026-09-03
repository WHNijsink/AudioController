from audio_controller import itec


def test_filter_usb_ports():
    names = ["ttyUSB0", "ttyUSB1", "tty", "sda", "ttyACM0", "ttyUSB"]
    assert itec._filter_usb_ports(names) == ["ttyUSB0", "ttyUSB1"]


def test_filter_usb_ports_empty():
    assert itec._filter_usb_ports(["sda", "null", "zero"]) == []
