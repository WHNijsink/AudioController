import os
import functools
import subprocess
import getpass

from audio_controller import envvars

# example output of running `aplay --list-devices`:
example_command_output = """
**** List of PLAYBACK Hardware Devices ****
card 0: Loopback [Loopback], device 0: Loopback PCM [Loopback PCM]
Subdevices: 8/8
Subdevice #0: subdevice #0
Subdevice #1: subdevice #1
Subdevice #2: subdevice #2
Subdevice #3: subdevice #3
Subdevice #4: subdevice #4
Subdevice #5: subdevice #5
Subdevice #6: subdevice #6
Subdevice #7: subdevice #7
card 0: Loopback [Loopback], device 1: Loopback PCM [Loopback PCM]
Subdevices: 8/8
Subdevice #0: subdevice #0
Subdevice #1: subdevice #1
Subdevice #2: subdevice #2
Subdevice #3: subdevice #3
Subdevice #4: subdevice #4
Subdevice #5: subdevice #5
Subdevice #6: subdevice #6
Subdevice #7: subdevice #7
card 1: Headphones [bcm2835 Headphones], device 0: bcm2835 Headphones [bcm2835 Headphones]
Subdevices: 7/8
Subdevice #0: subdevice #0
Subdevice #1: subdevice #1
Subdevice #2: subdevice #2
Subdevice #3: subdevice #3
Subdevice #4: subdevice #4
Subdevice #5: subdevice #5
Subdevice #6: subdevice #6
Subdevice #7: subdevice #7
card 2: CODEC [USB Audio CODEC], device 0: USB Audio [USB Audio]
Subdevices: 1/1
Subdevice #0: subdevice #0
"""


def read_configuration(command_output: "list[str]") -> "dict[int, dict[list[int]]]":
    """
    Transform command output, like obtained by `aplay --list-devices` or `arecord --list-devices`,
    to a configuration.

    :param command_output: see 'example_command_output'

    :return: dict like: {card_nr: {"devices": [int], "name": name}} where card_nr is int value

    """
    result = {}
    subdevices = []  # should not be needed
    for line in command_output:
        if line.startswith("card "):
            i_from = len("card ")
            i_to = line.index(":")
            card_nr = int(line[i_from:i_to])
            i_from = i_to + 1
            i_to = line.index(",", i_from)
            name = line[i_from:i_to].strip()
            card = result.get(card_nr, {"devices": {}, "name": name})
            result[card_nr] = card
            i_from = line.index(", device ") + len(", device ")
            i_to = line.index(":", i_from)
            device_nr = int(line[i_from:i_to])
            subdevices = []
            card["devices"][device_nr] = subdevices
        elif line.startswith("Subdevice ") and "#" in line and ":" in line:
            i_from = line.index("#") + 1
            i_to = line.index(":")
            subdevice_nr = int(line[i_from:i_to])
            subdevices.append(subdevice_nr)
    return result


def get_example_configuration():
    command_output = example_command_output.splitlines()
    config = read_configuration(command_output)
    print(config)


def get_soundcard_configuration(cmd):
    try:
        output = subprocess.run(cmd, capture_output=True, text=True).stdout
    except FileNotFoundError:
        # aplay/arecord not installed (e.g. non-Pi host): degrade gracefully like os.popen did
        output = ""
    lines = [line.strip() for line in output.splitlines()]
    return read_configuration(lines)


def get_soundcard_configuration_play():
    return get_soundcard_configuration(["aplay", "--list-devices"])


def get_soundcard_configuration_record():
    return get_soundcard_configuration(["arecord", "--list-devices"])


def find_card(config: dict, name: str):
    for card_nr, card in config.items():
        if name.lower() in card["name"].lower():
            return card_nr, card
    return (None, None)


def get_loopback_card(config: dict):
    return find_card(config, "Loopback")


def ensure_loopback_card():
    config = get_soundcard_configuration_play()
    card_nr, card = get_loopback_card(config)
    if card is None:
        user = getpass.getuser()
        if user == "root":
            # command to create virtual card (no shell)
            print("modprobe snd-aloop")
            subprocess.run(["sudo", "modprobe", "snd-aloop"])
            config = get_soundcard_configuration_play()
            card_nr, card = get_loopback_card(config)
    return card_nr, card


def singleton(func):
    called = False
    result = None

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        nonlocal called, result
        if not called:
            result = func(*args, **kwargs)
            called = True
        return result

    return wrapper


@singleton
def get_soundcard_info():
    result = {}
    if envvars.USE_VIRTUAL_SOUNDCARD:
        ensure_loopback_card()
    config_play = get_soundcard_configuration_play()
    config_record = get_soundcard_configuration_record()
    real_card_record = find_card(config_record, envvars.REAL_SOUNDCARD_NAME)
    real_card_play = find_card(config_play, envvars.REAL_SOUNDCARD_NAME)
    if real_card_record[0] is not None:
        real_play_devices = real_card_play[1]["devices"]
        real_play_device_nr = list(real_play_devices.keys())[0]
        real_record_devices = real_card_record[1]["devices"]
        real_record_device_nr = list(real_record_devices.keys())[0]
        result["real_card"] = {
            "nr": real_card_record[0],  # is same for play
            "devices": {
                "play": {
                    "nr": real_play_device_nr,
                    "subdevices": real_play_devices[real_play_device_nr],
                },
                "record": {
                    "nr": real_record_device_nr,
                    "subdevices": real_record_devices[real_record_device_nr],
                },
            },
        }

    if envvars.USE_VIRTUAL_SOUNDCARD:
        virtual_card_record = get_loopback_card(config_record)
        virtual_card_play = get_loopback_card(config_play)
        if virtual_card_record[0] is not None:
            virtual_play_devices = virtual_card_play[1]["devices"]
            virtual_play_device_nr = list(virtual_play_devices.keys())[0]
            virtual_record_devices = virtual_card_record[1]["devices"]
            # virtual card has device 0 and 1 on both play and record cards,
            # but 0 should be used to play, and 1 to record
            virtual_record_device_nr = list(virtual_record_devices.keys())[-1]
            result["virtual_card"] = {
                "nr": virtual_card_record[0],  # is same for play
                "devices": {
                    "play": {
                        "nr": virtual_play_device_nr,
                        "subdevices": virtual_play_devices[virtual_play_device_nr],
                    },
                    "record": {
                        "nr": virtual_record_device_nr,
                        "subdevices": virtual_record_devices[virtual_record_device_nr],
                    },
                },
            }
    return result


def device_string(interface: str, card: int, device: int = None, subdevice: int = None):
    """
    see https://en.wikipedia.org/wiki/Advanced_Linux_Sound_Architecture

    Copied about interface:
    A card's interface is a description of an ALSA protocol for accessing the card;
    possible interfaces include: hw, plughw, default, and plug:dmix.
    The hw interface provides direct access to the kernel device, but no software mixing or stream adaptation support.
    The plughw and default enable sound output where the hw interface would produce an error.

    """
    result = f"{interface}:{card}"
    if device is not None:
        result += f",{device}"
        if subdevice is not None:
            result += f",{subdevice}"
    return result


def get_real_device(play_or_record: str):
    soundcard_info = get_soundcard_info()
    interface = "hw"
    if play_or_record == "play":
        interface = "plughw"
    card = soundcard_info["real_card"]
    card_nr = card["nr"]
    device_nr = card["devices"][play_or_record]["nr"]
    subdevice_nr = card["devices"][play_or_record]["subdevices"][0]
    return device_string(interface, card_nr, device_nr, subdevice_nr)


def get_virtual_devices(play_or_record: str) -> "list[str]":
    soundcard_info = get_soundcard_info()
    interface = "hw"
    if play_or_record == "play":
        interface = "plughw"
    card = soundcard_info["virtual_card"]
    card_nr = card["nr"]
    device_nr = card["devices"][play_or_record]["nr"]
    subdevices = card["devices"][play_or_record]["subdevices"]
    result = []
    for i in range(0, min(envvars.MAX_OUTPUT_URL_STREAMS, len(subdevices))):
        subdevice_nr = subdevices[i]
        result.append(device_string(interface, card_nr, device_nr, subdevice_nr))
    return result


def get_real_play_device() -> str:
    return get_real_device("play")


def get_real_record_device() -> str:
    return get_real_device("record")


def get_virtual_play_devices() -> "list[str]":
    return get_virtual_devices("play")


def get_virtual_record_devices() -> "list[str]":
    return get_virtual_devices("record")


if __name__ == "__main__":
    # get_example_configuration()
    # print("Soundcards to play:")
    # print(get_soundcard_configuration_play())
    # print("Soundcards to record:")
    # print(get_soundcard_configuration_record())
    # loopback_card = ensure_loopback_card()
    info = get_soundcard_info()

    print("done")
