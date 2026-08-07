function(uv_venv)
    find_package(ament_cmake_venv REQUIRED)

    set(options)
    set(oneValueArgs DIRECTORY PROJECTFILE)
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

    set(_stamp "${venv_dir}/.built")
    set(_cmd
        "export PYTHONPATH=''"
        "cd ${venv_build_dir}"
        "uv venv --clear ${venv_dir}"
        ". ${venv_dir}/bin/activate"
        "uv pip install${_override_args} ${venv_build_dir}"
        "touch ${_stamp}"
    )

    list(JOIN _cmd " && " _cmd)

    add_custom_command(
        OUTPUT "${_stamp}"
        DEPENDS "${_synced}"
        COMMAND sh -c "${_cmd}"
        VERBATIM
    )

    add_custom_target("${target_venv}" ALL
        DEPENDS "${_stamp}"
    )

    venv_install()
endfunction()