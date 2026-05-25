execute_process(
    COMMAND uv --version
    RESULT_VARIABLE UV_RC
    OUTPUT_VARIABLE UV_VERSION_RAW
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
if(NOT UV_RC EQUAL 0)
    message(FATAL_ERROR "uv installation not found. https://docs.astral.sh/uv/getting-started/installation/")
endif()
unset(UV_RC)

# `uv venv` reads `requires-python` from pyproject.toml and auto-downloads the
# matching Python interpreter, stabilized in uv 0.3.0 (2024-08-20).
string(REGEX MATCH "[0-9]+\\.[0-9]+\\.[0-9]+" UV_VERSION "${UV_VERSION_RAW}")
set(UV_MIN_VERSION "0.3.0")
if(UV_VERSION VERSION_LESS UV_MIN_VERSION)
    message(FATAL_ERROR
        "ament_cmake_venv_uv requires uv >= ${UV_MIN_VERSION} (found ${UV_VERSION}). "
        "Upgrade: curl -LsSf https://astral.sh/uv/install.sh | sh"
    )
endif()
unset(UV_VERSION_RAW)
unset(UV_VERSION)
unset(UV_MIN_VERSION)

include("${ament_cmake_venv_uv_DIR}/uv_venv.cmake")
