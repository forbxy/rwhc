import subprocess
import wexpect
import time
import sys
import re
import os
import numpy as np

class ColorReader:
    def __init__(self, args):
        self.args_list = args
        base_dir = os.path.dirname(os.path.abspath(__file__))
        execute = os.path.join(base_dir, "bin", "spotread.exe")
        self.instance = wexpect.spawn(execute, [self.args_list],
                                    env=os.environ.copy(), timeout=10)
        self.status = "init"
        s = ""
        timeout = 15
        start = time.time()
        while 1:
            try:
                ret = self.instance.read_nonblocking()
                if ret:
                    s += ret
            except wexpect.EOF:
                raise RuntimeError("spotread exit unexpectedly")
            if time.time() - start > timeout:
                raise TimeoutError("init ColorReader time out")
            if "key to take a reading:" in s:
                self.status = "ready"
                break
            if "Spot read needs a calibration before continuing" in s:
                self.status = "need_calibration"
                break
    
    def calibrate(self):
        self.instance.send("x")
        s = ""
        timeout = 15
        start = time.time()
        while 1:
            try:
                ret = self.instance.read_nonblocking(size=1000)
                if ret:
                    s += ret
            except wexpect.EOF:
                raise RuntimeError("spotread exit unexpectedly during calibration")
            if "key to take a reading:" in s:
                self.status = "ready"
                break
            if "Calibration failed" in s:
                self.status = "need_calibration"
                break
            time.sleep(0.0001)
            if time.time() - start > timeout:
                raise TimeoutError("calibrate time out")
        return

    def read_XYZ(self):
        self.instance.send("x")
        # Implement an expect-like mechanism to facilitate checking spotread's output.
        s = ""
        timeout = 30
        start = time.time()
        while 1:
            ret = self.instance.read_nonblocking(size=1000)
            s += ret
            if "Place instrument on" in s:
                for itm in s.splitlines():
                    if "Result is XYZ:" in itm:
                        s = itm
                        match = re.search(r"XYZ: (.+), Yxy: (.+)", s)
                        return np.array([float(itm) for itm in match.group(1).split(" ")])
                break
            time.sleep(0.0001)
            if time.time() - start > timeout:
                raise TimeoutError("read XYZ time out")
        return 

    def terminate(self):
        self.instance.send("q")
        self.instance.send("q")
        s = ""
        timeout = 50
        start = time.time()
        while 1:
            try:
                ret = self.instance.read_nonblocking()
                if ret:
                    s += ret
            except wexpect.EOF:
                # print(time.time()-start)
                print(s)
                break
            time.sleep(0.0001)
            if time.time() - start > timeout:
                raise TimeoutError("terminate time out")
        return

class ColorWriter:
    def __init__(self, mode="hdr_10"):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        execute = os.path.join(base_dir, "bin", "dogegen.exe")
        self.instance = subprocess.Popen(
            [execute],                
            stdin=subprocess.PIPE,     
            stdout=subprocess.PIPE,    
            stderr=subprocess.PIPE, 
            text=True,                              
        )
        self.mode = mode
        if self.mode == "hdr_10":
            # 10bit HDR，0-1023
            self.instance.stdin.write("mode 10_hdr \n")  
        elif self.mode == "hdr_8":
            # 8bit HDR，0-255
            self.instance.stdin.write("mode 8_hdr \n") 
        elif self.mode == "sdr_10":
            self.instance.stdin.write("mode 10 \n")
        elif self.mode == "sdr_8":
            self.instance.stdin.write("mode 8 \n")
        self.instance.stdin.flush()
        self.instance.stdout.readline()
        self.count = 0

    def write_rgb(self, rgb, delay=0):
        command = f"window 100 {rgb[0]} {rgb[1]} {rgb[2]} \r\n"
        self.instance.stdin.write(command)
        self.instance.stdin.flush()
        ret = self.instance.stdout.readline()
        self.count += 1
        time.sleep(delay)

    def write_grayscale(self, color="white"):
        rgb_target = {"white": (1, 1, 1),
                      "red":   (1, 0, 0),
                      "green": (0, 1, 0),
                      "blue":  (0, 0, 1)}.get(color)
        if rgb_target is None:
            raise ValueError(f"Unknown color: {color}")
        
        if self.mode in ["hdr_10", "sdr_10"]:
            rgb_real = [itm * 1023 for itm in rgb_target]
            
        elif self.mode in ["hdr_8", "sdr_8"]:
            rgb_real = [itm * 255 for itm in rgb_target]
        command = f"draw -1 1 1 -1 0 0 0 {rgb_real[0]} {rgb_real[1]} {rgb_real[2]} 0 0 0 {rgb_real[0]} {rgb_real[1]} {rgb_real[2]} 1 \r\n"
        self.instance.stdin.write(command)
        self.instance.stdin.flush()
        ret = self.instance.stdout.readline()

    def terminate(self):
        if self.instance.poll() is None:
            self.instance.terminate()