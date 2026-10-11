function(uv_venv)
    find_package(ament_cmake_venv REQUIRED)

    set(options)
    set(oneValueArgs DIRECTORY PROJECTFILE TEST_EXTRA)
    set(multiValueArgs)
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

    set(_synced "${CMAKE_CURRENT_BINARY_DIR}/venv_build.stamp")

    file(GLOB_RECURSE _project_files CONFIGURE_DEPENDS "${PROJECT_DIRECTORY}/*")
    list(FILTER _project_files EXCLUDE REGEX "/(\\.git|\\.venv|\\.ruff_cache|__pycache__|[^/]+\\.egg-info)/|\\.pyc$")

    add_custom_command(
        OUTPUT "${_synced}"
        DEPENDS "${PROJECT_DIRECTORY}/${arg_PROJECTFILE}" ${_project_files}
        COMMAND ${CMAKE_COMMAND} -E rm -rf "${venv_build_dir}"
        COMMAND ${CMAKE_COMMAND} -E make_directory "${venv_build_dir}"
        COMMAND cp -a "${PROJECT_DIRECTORY}/." "${venv_build_dir}/"
        COMMAND ${CMAKE_COMMAND} -E rm -rf "${venv_build_dir}/.git"
        COMMAND ${CMAKE_COMMAND} -E touch "${_synced}"
    )

    set(_override_args "")
    string(REPLACE ":" ";" _override_paths "$ENV{AMENT_CMAKE_VENV_UV_OVERRIDES}")
    foreach(_path IN LISTS _override_paths)
        if(_path)
            string(APPEND _override_args " --override ${_path}")
        endif()
    endforeach()

    set(_spec "${venv_build_dir}")
    set(_spec_file "")
    if(DEFINED arg_TEST_EXTRA)
        if(BUILD_TESTING)
            set(_spec "${venv_build_dir}[${arg_TEST_EXTRA}]")
        endif()
        set(_spec_file "${CMAKE_CURRENT_BINARY_DIR}/venv_spec.txt")
        file(CONFIGURE OUTPUT "${_spec_file}" CONTENT "${_spec}\n")
    endif()

    set(_stamp "${venv_dir}/.built")
    set(_cmd
        "export PYTHONPATH=''"
        "cd ${venv_build_dir}"
        "uv venv --clear ${venv_dir}"
        ". ${venv_dir}/bin/activate"
        "uv pip install${_override_args} '${_spec}'"
        "touch ${_stamp}"
    )

    list(JOIN _cmd " && " _cmd)

    add_custom_command(
        OUTPUT "${_stamp}"
        DEPENDS "${_synced}" ${_spec_file}
        COMMAND sh -c "${_cmd}"
        VERBATIM
    )

    add_custom_target("${target_venv}" ALL
        DEPENDS "${_stamp}"
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