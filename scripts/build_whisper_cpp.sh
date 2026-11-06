#!/usr/bin/env bash
# Builds whisper.cpp with Vulkan on Linux: the speech engine Ghostwriter uses on any graphics card.
#
# Only the PC that builds it needs the tools: git, CMake, a C++ compiler, the Vulkan and SPIR-V headers, and glslc.
# On Arch:
#   sudo pacman -S --needed git cmake gcc vulkan-headers spirv-headers shaderc
# People who install Ghostwriter just download the finished files.
#
#   scripts/build_whisper_cpp.sh [version]
#
# The source goes in .tools/, and the finished programs land in .whisper-cpp/. The archive it makes in .tools/ is what
# the Linux installer downloads: upload it to the GitHub prerelease named whisper-cpp-<version>.
# Set JOBS to build with fewer processor cores on a machine short on memory.

set -euo pipefail

version="${1:-v1.9.5}"
project="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source="$project/.tools/whisper.cpp-$version"
build="$source/build"
output="$project/.whisper-cpp"

if [[ ! -d "$source" ]]; then
    git clone --quiet --depth 1 --branch "$version" https://github.com/ggml-org/whisper.cpp "$source"
fi

# The processor code is built once for each generation of x86 processor, and whisper.cpp loads the best one this PC
# can run when it starts. A single build for newer processors crashes on ones without AVX, like budget Celerons.
# $ORIGIN lets the programs find their libraries next to them, wherever the folder ends up.
cmake -S "$source" -B "$build" -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON -DGGML_NATIVE=OFF \
    -DBUILD_SHARED_LIBS=ON -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON -DCMAKE_INSTALL_RPATH='$ORIGIN' \
    -DWHISPER_BUILD_TESTS=OFF -DWHISPER_SDL2=OFF
cmake --build "$build" --parallel "${JOBS:-$(nproc)}"

rm -rf "$output"
mkdir -p "$output"
cp "$build/bin/whisper-server" "$build/bin/whisper-cli" "$output/"
find "$build" \( -name 'libggml*.so*' -o -name 'libwhisper.so*' \) -exec cp -P {} "$output/" \;
cp "$source/LICENSE" "$output/LICENSE.txt"
printf '%s\n' "$version" > "$output/VERSION.txt"
echo "Built whisper.cpp $version with Vulkan into $output"

# Ghostwriter only uses the server and the libraries it loads, so that's all that goes in the download.
archive="$project/.tools/whisper-cpp-$version-vulkan-linux-x64.tar.gz"
(cd "$output" && tar -czf "$archive" whisper-server libggml*.so* libwhisper.so* LICENSE.txt VERSION.txt)
echo "Release download: $archive"
