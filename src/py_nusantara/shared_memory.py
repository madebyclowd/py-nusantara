import os
import logging
import pickle
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("py_nusantara")


class SharedMemoryCache:
    """A shared memory cache backend using Python's native multiprocessing.shared_memory.
    
    Stores pickled python objects in shared memory segments, prefixing each with its size.
    """

    _registered_keys = set()

    def __init__(self, prefix: str = "nusantara_shm") -> None:
        self.prefix = prefix

    def _sanitize_key(self, key: str) -> str:
        # POSIX shared memory names must start with a slash '/' on some OS,
        # but Python's multiprocessing.shared_memory strips it or manages it.
        # We replace characters that are unsafe for segment naming.
        sanitized = f"{self.prefix}_{key}".replace(".", "_").replace("/", "_")
        return sanitized

    def get(self, key: str) -> Optional[Any]:
        from multiprocessing import shared_memory
        name = self._sanitize_key(key)
        shm = None
        try:
            shm = shared_memory.SharedMemory(name=name)
            # Read first 8 bytes for size
            size = int.from_bytes(shm.buf[:8], byteorder="big")
            data_bytes = bytes(shm.buf[8:8+size])
            return pickle.loads(data_bytes)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.debug(f"Failed to read from shared memory '{name}': {e}")
            return None
        finally:
            if shm is not None:
                try:
                    shm.close()
                except Exception:
                    pass

    def set(self, key: str, value: Any) -> None:
        from multiprocessing import shared_memory
        name = self._sanitize_key(key)
        try:
            data_bytes = pickle.dumps(value)
            size = len(data_bytes)
            
            # Clean up existing block first if it exists
            try:
                existing = shared_memory.SharedMemory(name=name)
                existing.close()
                existing.unlink()
            except Exception:
                pass

            shm = shared_memory.SharedMemory(name=name, create=True, size=8 + size)
            shm.buf[:8] = size.to_bytes(8, byteorder="big")
            shm.buf[8:8+size] = data_bytes
            shm.close()
            
            self._registered_keys.add(key)
        except Exception as e:
            logger.debug(f"Failed to write to shared memory '{name}': {e}")

    def unlink(self, key: str) -> None:
        from multiprocessing import shared_memory
        name = self._sanitize_key(key)
        try:
            shm = shared_memory.SharedMemory(name=name)
            shm.close()
            shm.unlink()
        except Exception:
            pass

    def unlink_all(self) -> None:
        # 1. Unlink explicitly tracked keys
        for key in list(self._registered_keys):
            self.unlink(key)
        self._registered_keys.clear()

        # 2. Scanning /dev/shm on Linux for safety
        shm_dir = Path("/dev/shm")
        if shm_dir.exists() and shm_dir.is_dir():
            for p in shm_dir.glob(f"{self.prefix}_*"):
                try:
                    p.unlink()
                except Exception as e:
                    logger.debug(f"Failed to unlink shared memory file {p}: {e}")
