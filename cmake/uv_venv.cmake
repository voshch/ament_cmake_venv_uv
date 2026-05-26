function(uv_venv)
    find_package(ament_cmake_venv REQUIRED)

    set(options)
    set(oneValueArgs DIRECTORY)
    set(multiValueArgs)
    cmake_parse_arguments(PARSE_ARGV 0 arg
        "${options}" "${oneValueArgs}" "${multiValueArgs}"
    )

    if(NOT DEFINED arg_DIRECTORY)
        set(arg_DIRECTORY .)
    endif()

    set(PROJECT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/${arg_DIRECTORY}")
    
    add_custom_command(
        OUTPUT "${venv_build_dir}/${arg_NAME}"
        DEPENDS "${PROJECT_DIRECTORY}/${arg_PROJECTFILE}"
        COMMAND ${CMAKE_COMMAND} -E make_directory "${venv_build_dir}"
        COMMAND cp -a "${PROJECT_DIRECTORY}/." "${venv_build_dir}/"
    )

    set(_stamp "${venv_dir}/.built")
    set(_cmd
        "export PYTHONPATH=''"
        "cd ${venv_build_dir}"
        "uv venv --clear ${venv_dir}"
        ". ${venv_dir}/bin/activate"
        "uv pip install ${venv_build_dir}"
        "touch ${_stamp}"
    )

    list(JOIN _cmd " && " _cmd)

    add_custom_command(
        OUTPUT "${_stamp}"
        DEPENDS "${venv_build_dir}"
        COMMAND sh -c "${_cmd}"
        VERBATIM
    )

    add_custom_target("${target_venv}" ALL
        DEPENDS "${_stamp}"
    )

    venv_install()
endfunction()