"""Test sandbox AST validation."""
import pytest
from empire.registry.sandbox import Sandbox, SecurityError


class TestSandboxAST:
    """Test that sandbox blocks dangerous code."""
    
    def setup_method(self):
        self.sandbox = Sandbox(profile="standard")
    
    def test_blocks_import_subprocess(self, unsafe_python_code):
        """Should block code that imports subprocess."""
        with pytest.raises(SecurityError):
            self.sandbox.validate(unsafe_python_code)
    
    def test_blocks_os_system(self):
        """Should block os.system calls."""
        code = "import os\nos.system('ls')"
        with pytest.raises(SecurityError):
            self.sandbox.validate(code)
    
    def test_blocks_exec_call(self):
        """Should block exec()."""
        code = "exec('print(1)')"
        with pytest.raises(SecurityError):
            self.sandbox.validate(code)
    
    def test_blocks_eval_call(self):
        """Should block eval()."""
        code = "x = eval('1+1')"
        with pytest.raises(SecurityError):
            self.sandbox.validate(code)
    
    def test_blocks_open_call(self):
        """Should block open() outside allowed paths."""
        code = "f = open('/etc/passwd')"
        with pytest.raises(SecurityError):
            self.sandbox.validate(code)
    
    def test_blocks_socket(self):
        """Should block socket imports."""
        code = "import socket\ns = socket.socket()"
        with pytest.raises(SecurityError):
            self.sandbox.validate(code)
    
    def test_blocks_pickle(self):
        """Should block pickle imports."""
        code = "import pickle\npickle.loads(b'...')"
        with pytest.raises(SecurityError):
            self.sandbox.validate(code)
    
    def test_blocks_ctypes(self):
        """Should block ctypes imports."""
        code = "import ctypes\nctypes.cdll.LoadLibrary('libc')"
        with pytest.raises(SecurityError):
            self.sandbox.validate(code)
    
    def test_blocks_fork(self):
        """Should block fork()."""
        code = "import os\npid = os.fork()"
        with pytest.raises(SecurityError):
            self.sandbox.validate(code)
    
    def test_allows_safe_code(self, safe_python_code):
        """Should allow safe arithmetic code."""
        # Should not raise
        self.sandbox.validate(safe_python_code)
    
    def test_allows_math(self):
        """Should allow math operations."""
        code = """
import math
x = math.sqrt(16)
y = sum([1, 2, 3])
"""
        self.sandbox.validate(code)
    
    def test_allows_json(self):
        """Should allow json operations."""
        code = """
import json
data = json.dumps({"x": 1})
parsed = json.loads(data)
"""
        self.sandbox.validate(code)


class TestSandboxExecution:
    """Test sandbox code execution."""
    
    def test_runs_safe_code(self, safe_python_code):
        """Should run safe code and return result."""
        sandbox = Sandbox(profile="standard")
        result = sandbox.run(safe_python_code, inputs={"x": 5})
        assert result == {"doubled": 10, "squared": 25}
    
    def test_enforces_timeout(self):
        """Should kill long-running code."""
        code = """
import time
time.sleep(10)
"""
        sandbox = Sandbox(profile="standard", timeout=1)
        with pytest.raises(TimeoutError):
            sandbox.run(code)
    
    def test_enforces_memory_limit(self):
        """Should kill code that uses too much memory."""
        code = """
x = [1] * (10 ** 8)  # 100M ints ~ 800MB
"""
        sandbox = Sandbox(profile="standard", memory_limit_mb=100)
        with pytest.raises(MemoryError):
            sandbox.run(code)
