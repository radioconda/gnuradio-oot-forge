#!/usr/bin/env bash

set -ex

cmake -E make_directory buildconda
cd buildconda

cmake_config_args=(
    -DLIB_SUFFIX=""
    -DENABLE_DOXYGEN=OFF
    -DENABLE_TESTING=ON
)

cmake ${CMAKE_ARGS} -G "Ninja" .. "${cmake_config_args[@]}"
cmake --build . --config Release -- -j${CPU_COUNT}
cmake --build . --config Release --target install

# FIXME: don't run any tests because they exist but are basically empty and broken
#if [[ "${CONDA_BUILD_CROSS_COMPILATION:-}" != "1" || "${CROSSCOMPILING_EMULATOR}" != "" ]]; then
#    ctest --build-config Release --output-on-failure --timeout 120 -j${CPU_COUNT}
#fi

# clean up fontconfig cache generated during testing so it's not in package
if [[ $target_platform == linux* ]] ; then
    rm -rf $PREFIX/var/cache
fi
