function(uv_venv)
    find_package(ament_cmake_venv REQUIRED)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)

    set(options)
    set(oneValueArgs DIRECTORY PROJECTFILE TEST_EXTRA)
    set(multiValueArgs POST_INSTALL)
    cmake_parse_arguments(PARSE_ARGV 0 arg
        "${options}" "${oneValueArgs}" "${multiValueArgs}"
    )

    if(NOT DEFINED arg_DIRECTORY)
        set(arg_DIRECTORY .)
    endif()

    if(NOT DEFINED arg_PROJECTFILE)
        set(arg_PROJECTFILE pyproject.toml)
    endif()

    set(PROJECT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/${arg_DIRECTORY}")
    if(NOT EXISTS "${PROJECT_DIRECTORY}/${arg_PROJECTFILE}")
        message(FATAL_ERROR "uv_venv: no ${arg_PROJECTFILE} in ${PROJECT_DIRECTORY}")
    endif()

    set(_args "${PROJECT_DIRECTORY}" "${venv_build_dir}" "${venv_dir}")
    if(DEFINED arg_TEST_EXTRA AND BUILD_TESTING)
        list(APPEND _args --extra "${arg_TEST_EXTRA}")
    endif()
    foreach(_post IN LISTS arg_POST_INSTALL)
        list(APPEND _args --post-install "${_post}")
    endforeach()

    add_custom_target("${target_venv}" ALL
        COMMAND "${Python3_EXECUTABLE}" "${ament_cmake_venv_uv_DIR}/uv_venv_store.py" ${_args}
        VERBATIM
    )

    venv_install()
endfunction()

function(uv_venv_pytest testname path)
    set(options)
    set(oneValueArgs TIMEOUT)
    set(multiValueArgs)
    cmake_parse_arguments(PARSE_ARGV 2 arg
        "${options}" "${oneValueArgs}" "${multiValueArgs}"
    )

    if(NOT IS_ABSOLUTE "${path}")
        set(path "${CMAKE_CURRENT_SOURCE_DIR}/${path}")
    endif()

    if(NOT DEFINED arg_TIMEOUT)
        set(arg_TIMEOUT 60)
    endif()

    set(_result "${AMENT_TEST_RESULTS_DIR}/${PROJECT_NAME}/${testname}.xunit.xml")
    ament_add_test("${testname}"
        COMMAND ${venv_clean_pythonpath} "${venv_python_bin}" -u -m pytest "${path}"
            -o "cache_dir=${CMAKE_CURRENT_BINARY_DIR}/uv_venv_pytest/${testname}/.cache"
            "--junit-xml=${_result}"
            "--junit-prefix=${PROJECT_NAME}"
        OUTPUT_FILE "${CMAKE_BINARY_DIR}/uv_venv_pytest/${testname}.txt"
        RESULT_FILE "${_result}"
        TIMEOUT ${arg_TIMEOUT}
    )
endfunction()