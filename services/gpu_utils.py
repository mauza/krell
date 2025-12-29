"""
GPU Detection and Selection Utilities.

This module provides automatic GPU detection and selection for PyTorch workloads.
Supports:
- NVIDIA GPUs via CUDA
- Apple M-series GPUs via MPS (Metal Performance Shaders)
- Intel GPUs via XPU (Intel Extension for PyTorch)
- CPU fallback when no GPU is available
"""

import logging
import platform
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import torch

logger = logging.getLogger(__name__)


class GPUType(Enum):
    """Enumeration of supported GPU types."""

    CUDA = "cuda"  # NVIDIA GPUs
    MPS = "mps"  # Apple Metal Performance Shaders (M-series)
    XPU = "xpu"  # Intel GPUs (via Intel Extension for PyTorch)
    CPU = "cpu"  # CPU fallback


@dataclass
class GPUInfo:
    """Information about a detected GPU."""

    gpu_type: GPUType
    device_string: str
    device_name: str
    memory_total: Optional[int] = None  # in bytes
    memory_free: Optional[int] = None  # in bytes

    def __str__(self) -> str:
        mem_info = ""
        if self.memory_total:
            mem_gb = self.memory_total / (1024**3)
            mem_info = f", {mem_gb:.1f}GB"
        return f"{self.device_name} ({self.gpu_type.value}{mem_info})"


def _check_cuda_available() -> Optional[GPUInfo]:
    """Check if CUDA (NVIDIA GPU) is available."""
    try:
        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            if device_count > 0:
                # Use the first available CUDA device
                device_name = torch.cuda.get_device_name(0)
                props = torch.cuda.get_device_properties(0)
                return GPUInfo(
                    gpu_type=GPUType.CUDA,
                    device_string="cuda",
                    device_name=device_name,
                    memory_total=props.total_memory,
                    memory_free=None,  # Would need additional call to get free memory
                )
    except Exception as e:
        logger.debug(f"CUDA check failed: {e}")
    return None


def _check_mps_available() -> Optional[GPUInfo]:
    """Check if MPS (Apple Metal) is available."""
    try:
        # MPS is only available on macOS with Apple Silicon
        if platform.system() != "Darwin":
            return None

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            # Check if MPS is actually built into this PyTorch version
            if torch.backends.mps.is_built():
                # Get chip name from system
                import subprocess

                try:
                    result = subprocess.run(
                        ["sysctl", "-n", "machdep.cpu.brand_string"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    chip_name = result.stdout.strip() or "Apple Silicon"
                except Exception:
                    chip_name = "Apple Silicon"

                return GPUInfo(
                    gpu_type=GPUType.MPS,
                    device_string="mps",
                    device_name=chip_name,
                    memory_total=None,  # MPS doesn't expose memory info easily
                    memory_free=None,
                )
    except Exception as e:
        logger.debug(f"MPS check failed: {e}")
    return None


def _check_xpu_available() -> Optional[GPUInfo]:
    """Check if XPU (Intel GPU) is available."""
    try:
        # Intel Extension for PyTorch (IPEX) provides XPU support
        # First check if ipex is available
        try:
            import intel_extension_for_pytorch as ipex  # noqa: F401

            has_ipex = True
        except ImportError:
            has_ipex = False

        if has_ipex and hasattr(torch, "xpu") and torch.xpu.is_available():
            device_count = torch.xpu.device_count()
            if device_count > 0:
                device_name = torch.xpu.get_device_name(0)
                props = torch.xpu.get_device_properties(0)
                return GPUInfo(
                    gpu_type=GPUType.XPU,
                    device_string="xpu",
                    device_name=device_name,
                    memory_total=getattr(props, "total_memory", None),
                    memory_free=None,
                )
    except Exception as e:
        logger.debug(f"XPU check failed: {e}")
    return None


def detect_available_gpus() -> list[GPUInfo]:
    """
    Detect all available GPU types on the system.

    Returns:
        List of GPUInfo objects for each available GPU type.
        Empty list if only CPU is available.
    """
    available = []

    # Check each GPU type
    cuda_info = _check_cuda_available()
    if cuda_info:
        available.append(cuda_info)
        logger.debug(f"Found CUDA device: {cuda_info}")

    mps_info = _check_mps_available()
    if mps_info:
        available.append(mps_info)
        logger.debug(f"Found MPS device: {mps_info}")

    xpu_info = _check_xpu_available()
    if xpu_info:
        available.append(xpu_info)
        logger.debug(f"Found XPU device: {xpu_info}")

    return available


def get_best_device() -> str:
    """
    Get the best available device for PyTorch operations.

    Priority order:
    1. CUDA (NVIDIA) - Most widely supported, best performance for most models
    2. MPS (Apple) - Good performance on Apple Silicon
    3. XPU (Intel) - Intel GPU acceleration
    4. CPU - Fallback when no GPU is available

    Returns:
        Device string suitable for torch.device() (e.g., "cuda", "mps", "xpu", "cpu")
    """
    available = detect_available_gpus()

    if not available:
        logger.info("No GPU detected, using CPU")
        return "cpu"

    # Return the first available (highest priority) GPU
    best = available[0]
    logger.info(f"Selected device: {best}")
    return best.device_string


def get_device_info(device: str) -> Optional[GPUInfo]:
    """
    Get information about a specific device.

    Args:
        device: Device string ("cuda", "mps", "xpu", "cpu", or "auto")

    Returns:
        GPUInfo if device is available, None otherwise
    """
    if device == "auto":
        available = detect_available_gpus()
        return (
            available[0]
            if available
            else GPUInfo(
                gpu_type=GPUType.CPU,
                device_string="cpu",
                device_name="CPU",
            )
        )

    if device == "cpu":
        return GPUInfo(
            gpu_type=GPUType.CPU,
            device_string="cpu",
            device_name="CPU",
        )

    if device == "cuda":
        return _check_cuda_available()
    elif device == "mps":
        return _check_mps_available()
    elif device == "xpu":
        return _check_xpu_available()

    return None


def resolve_device(device: str) -> str:
    """
    Resolve a device specification to an actual device string.

    Handles "auto" by detecting the best available device.
    Validates that the requested device is actually available.

    Args:
        device: Device specification ("auto", "cuda", "mps", "xpu", or "cpu")

    Returns:
        Resolved device string

    Raises:
        ValueError: If requested device is not available
    """
    if device == "auto":
        return get_best_device()

    if device == "cpu":
        return "cpu"

    # Validate that requested device is available
    info = get_device_info(device)
    if info is None:
        available = detect_available_gpus()
        available_str = ", ".join(g.device_string for g in available) or "cpu only"
        raise ValueError(
            f"Requested device '{device}' is not available. "
            f"Available devices: {available_str}"
        )

    return device


def log_device_info(device: str) -> None:
    """
    Log detailed information about the selected device.

    Args:
        device: Device string to log info for
    """
    info = get_device_info(device)
    if info:
        logger.info(f"Using device: {info}")
        if info.memory_total:
            logger.info(f"  Total memory: {info.memory_total / (1024**3):.1f} GB")
    else:
        logger.info(f"Using device: {device}")


def get_all_device_info() -> dict:
    """
    Get a summary of all available compute devices.

    Returns:
        Dictionary with device availability and info
    """
    result = {
        "available_gpus": [],
        "selected_device": get_best_device(),
        "cuda_available": torch.cuda.is_available(),
        "mps_available": (
            hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
            if platform.system() == "Darwin"
            else False
        ),
        "xpu_available": hasattr(torch, "xpu") and torch.xpu.is_available()
        if hasattr(torch, "xpu")
        else False,
    }

    for gpu in detect_available_gpus():
        result["available_gpus"].append(
            {
                "type": gpu.gpu_type.value,
                "device": gpu.device_string,
                "name": gpu.device_name,
                "memory_total_gb": (
                    gpu.memory_total / (1024**3) if gpu.memory_total else None
                ),
            }
        )

    return result
