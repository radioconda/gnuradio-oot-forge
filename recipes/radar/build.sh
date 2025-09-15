#!/usr/bin/env bash

set -ex

cmake -E make_directory buildconda
cd buildconda

if [[ "${target_platform}" != "${build_platform}" ]]; then
    rm -f "${PREFIX}/bin/moc"
    ln -s "${BUILD_PREFIX}/bin/moc" "${PREFIX}/bin/moc"

    echo "Removed: ${PREFIX}/bin/moc"
    echo "Linked to: ${BUILD_PREFIX}/bin/moc"
fi

cmake_config_args=(
    -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_INSTALL_PREFIX=$PREFIX
    -DCMAKE_PREFIX_PATH=$PREFIX
    -DLIB_SUFFIX=""
    -DENABLE_DOXYGEN=OFF
    -DENABLE_TESTING=ON
)

cmake ${CMAKE_ARGS} -G "Ninja" .. "${cmake_config_args[@]}"
cmake --build . --config Release -- -j${CPU_COUNT}
cmake --build . --config Release --target install

if [[ "${CONDA_BUILD_CROSS_COMPILATION:-}" != "1" || "${CROSSCOMPILING_EMULATOR}" != "" ]]; then
    SKIP_TESTS=(
        qa_estimator_fmcw
        qa_msg_manipulator
        qa_tracking_singletarget
    )
    SKIP_TESTS_STR=$( IFS="|"; echo "^(${SKIP_TESTS[*]})$" )
    ctest --build-config Release --output-on-failure --timeout 120 -j${CPU_COUNT} -E "$SKIP_TESTS_STR"
    ctest --build-config Release --output-on-failure --timeout 120 -j${CPU_COUNT} -R "$SKIP_TESTS_STR" || true
fi

# clean up fontconfig cache generated during testing so it's not in package
if [[ $target_platform == linux* ]] ; then
    rm -rf $PREFIX/var/cache
fi
