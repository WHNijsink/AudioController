""" Functionality to create a shell process, and communicate with it. """

import time
import sys
import os
import select
import signal
import subprocess
from subprocess import Popen, PIPE
import threading as trd
from contextlib import contextmanager
from typing import List, Tuple, Dict, Union, Optional, Iterator


_shell_command = 'bash'  # command to run a shell (e.g. 'sh' or '/bin/bash')
_exit_line = 'shell_has_returned_with_code'


class ShellProcess():

    def __init__(self):
        """ Create a ShellProcess, which wraps a real shell process.
        """
        self._process: Popen = None
        self._in_context: bool = False
        self.silent: bool = None # print output of shell (True/False/None). Value can be 
        self.print_error: bool = True # print errors, even if silent == True
        self.print_commands: bool = True
        self.print_empty_lines: bool = True
        self.print_start_stop: bool = False
        self.has_timeout: bool = False # to indicate when execute has reached a timeout
        self.allow_user_input = False # allow user to give input during execution of commands
        

    def set_silent(self, value=None):
        """ Set default value to show or hide commands and results.

        :Parameters:
         - `value` is one of (True, False, None)
         """
        assert value is None or value == True or value == False
        self.silent = value

    def start(self):
        assert self._process is None, "Cannot start process which is not stopped"
        # bufsize must be zero to make sure output is directly returned when available:
        self._process = Popen(args=[_shell_command], stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=None, bufsize=0)
        if self.print_start_stop:
            print(f"Created shell process with pid={self._process.pid}")

    def stop(self):
        assert self._process is not None, "Cannot stop process which is not running"
        pid = self._process.pid
        os.kill(pid, signal.SIGTERM)
        self._process = None
        if self.print_start_stop:
            print(f"Stopped shell process with pid={pid}")
    
    def _read_line(self, timeout, silent:bool):
        """ read a stdout or stderror line from process, and return on first success
            returns a line or None
        """
        # streams to read
        str_in = sys.stdin
        str_out = self._process.stdout
        str_err = self._process.stderr

        if self.allow_user_input:
            r, _, _ = select.select([str_in, str_out, str_err], [], [], timeout)
        else:
            r, _, _ = select.select([str_out, str_err], [], [], timeout)

        if str_in in r:
            self._process.stdin.write(str_in.readline().encode())
            r, _, _ = select.select([str_out, str_err], [], [], timeout)

        if len(r) == 0:
            return None
        
        s = r[0]
        should_print = not silent or (s is str_err and self.print_error)

        # read complete line (blocking)
        if not self.allow_user_input:
            line = s.readline().decode(errors="replace").rstrip()
            if should_print and not line.startswith(_exit_line):
                print(line)
                sys.stdout.flush()
            return line

        # read char by char
        line = ""
        is_printing = False
        while s in r:
            char = s.read(1).decode(errors="replace")
            if char == "\n":
                if is_printing:
                    print(char, end=""); sys.stdout.flush()
                break
            line += char
            if is_printing:
                print(char, end=""); sys.stdout.flush()
            elif should_print and not line.startswith(_exit_line[:len(line)]):
                print(line, end=""); sys.stdout.flush()
                is_printing = True

            if str_in in r:
                # wait on user to finish input line, and write it to process, then exit reading line
                self._process.stdin.write(str_in.readline().encode())
                break

            r, _, _ = select.select([s, str_in], [], [], timeout)
        
        return line


    @contextmanager
    def __call__(self, stop_on_exception=False, show_time_elapsed=False) -> Iterator['ShellProcess']:
        """ Context manager to start and stop a shell process.

            p = ShellProcess()
            with p(stop_on_exception=True):
                p.execute('echo hello', timeout=1)

        """
        assert self._in_context == False, "Cannot create context on process twice"
        self._in_context = True
        if self._process is None:
            self.start()
        _stop = False
        raised = True  # for example a Keyboard Interupt
        try:
            pid = self._process.pid
            start = time.time()
            yield self
            _stop = True
            raised = False
        except Exception as e:
            print(f"Exception during shell process with pid={pid}: {str(e)}")
            if stop_on_exception:
                _stop = True
            raise e
        finally:
            self._in_context = False
            time_elapsed = time.time() - start
            if show_time_elapsed:
                print(f"Time elapsed (sec) of shell with pid={pid}: {time_elapsed}")
            if _stop or raised:
                self.stop()

    def execute(self, cmd: str, **kwargs) -> Union[List[str], Tuple[List[str], bool]]:
        """ Executes command in the shell process. Reads lines and prints them.

        If `allow_error` is False (default), an Exception is raised if errors are written.
        This can prevent execution of next statements.
        It can also kill current command, if `stop_on_exception` of this process context is True (default=False).

        :Parameters:
         - allow_error
         - silent
         - return_returncode
         - timeout

        """
        allow_error = kwargs.pop('allow_error', False)
        silent = kwargs.pop('silent', self.silent)
        return_returncode = kwargs.pop('return_returncode', False)
        timeout = kwargs.pop('timeout', None)

        assert len(kwargs) == 0, f"Illegal arguments provided: {kwargs}"

        lines = []

        if self.has_timeout:
            # previous call to this execute method has finished with timeout, so wait and flush buffer
            # read lines until line contains exit code
            while True:
                line = self._read_line(None, silent)
                if line is not None:
                    if line.startswith(_exit_line):
                        # return_code is not interesting anymore
                        break
                    lines.append(line)
            self.has_timeout = False

        if self._process is None:
            self.start()
        
        if timeout is not None:
            end_time = time.time() + timeout

        return_code = None
        if not silent and self.print_commands:
            if self.print_empty_lines:
                print()
            print(f"$ {cmd}")
            sys.stdout.flush()

        cmd = cmd.rstrip(' ;')
        cmd = cmd + f' ; echo "{_exit_line} $?"\n'

        self._process.stdin.write(cmd.encode())

        # read lines until line contains exit code, or timeout is reached
        while True:
            if timeout is not None:
                line = self._read_line(max(0.3, end_time - time.time()), silent)
            else:
                line = self._read_line(None, silent)
            if line is not None:
                if line.startswith(_exit_line):
                    return_code = int(line.split()[1])
                    if return_code != 0:
                        if not allow_error:
                            raise Exception("Shell process returned errors")
                    break
                lines.append(line)
            if timeout is not None and time.time() > end_time:
                self.has_timeout = True
                break # TODO raise exception, stop process, or leave it to the caller?

        if return_returncode:
            return (lines, return_code)
        return lines
    


_global_shell: ShellProcess = None


@contextmanager
def in_shell(stop_on_exception=False, show_time_elapsed=False) -> Iterator[ShellProcess]:
    p = global_shell()
    with p(stop_on_exception, show_time_elapsed):
        yield p


def global_shell() -> ShellProcess:
    """ Create global shell process, without using a context manager. Made for CLI usage. """
    global _global_shell
    if _global_shell is None:
        _global_shell = ShellProcess()
    return _global_shell


def execute(cmd: str, **kwargs):
    return global_shell().execute(cmd, **kwargs)


@contextmanager
def in_dir(path: str, p: ShellProcess = None, silent=True) -> Iterator[None]:
    """ run 'cd' command to given path, and after closing the context, switch back to current directory.

    Example for listing one directory up: 

        with in_dir(".."):
            execute("ls")

    """
    if p is None:
        p = global_shell()
    pwd = p.execute("pwd", silent=silent)[0]
    try:
        p.execute(f'cd "{path}"', silent=silent)
    except:
        print(f"Could not cd to path {path}")
        raise
    yield
    try:
        p.execute(f'cd "{pwd}"', silent=silent)
    except:
        print(f"Could not cd to path {pwd}")
        raise


if __name__ == '__main__':
    pass
