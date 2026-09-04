
import setuptools
import os
from pathlib import Path

with open("README.md", "r") as fh:
    long_description = fh.read()


# def package_data():
#     """ Return list of directories to include for installation.
#     For each item in the returned list, only give the relative path, with respect to this package directory. """
#     result = []
#     package_dir = Path(os.path.dirname(os.path.abspath(__file__))) / 'mbase'
#     parts = list(package_dir.parts)
#     length = len(parts)

#     dirs = ['db_users']

#     for d in dirs:
#         files = package_dir.glob(d + "/**")
#         for f in files:
#             if f.is_dir():
#                 ps = f.parts[length:]
#                 if not '__pycache__' in ps:
#                     path = os.path.join(*ps)
#                     if not path in result:
#                         result.append(path)
#                         # print(path)

#     result = [r + '/*' for r in result]
#     return result


setuptools.setup(
    name="audio_controller",
    version="1.0.0",
    author="",
    author_email="",
    description="",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="",
    packages=setuptools.find_packages(),
    # Runtime dependencies. Build/dev-only tools (transcrypt, watchdog, pytest,
    # pylint, black) are intentionally not listed here; create_venv.sh installs
    # those. 'requests' is used directly (camera/SSRF checks) and no longer relies
    # on being pulled in transitively by onvif-zeep.
    # Pin secure floors with compatible ranges (S-M8). Lower bounds keep a fresh
    # Pi build off known-vulnerable releases; upper bounds avoid a surprise major.
    # The ranges stay Python 3.7-installable (the Pi): Tornado 6.2 is the last 3.7
    # build, while a 3.9+ dev box resolves to 6.5.
    install_requires=[
        "tornado>=6.1,<7",
        "python-socketio>=5.5,<6",
        "python-engineio>=4.4,<5",
        "pyserial>=3.5",
        "python-decouple>=3.6",
        "onvif-zeep>=0.2.12",
        "requests>=2.31,<3",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    #package_data={'audio_controller': package_data()},
)
