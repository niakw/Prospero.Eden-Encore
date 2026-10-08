#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""PS5 HTTPS uses Eden's complete pinned CA bundle and Encore identifies Nlib requests."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cmake = (root / "headless/CMakeLists.txt").read_text()
build = (root / "tools/build-headless-native.sh").read_text()
materialize = (root / "tools/materialize-openssl-cert.py").read_text()
patch = (root / "headless/backports/eden-ps5-net-user-agent.patch").read_text()
apply = (root / "tools/apply-eden-backports.sh").read_text()
link = (root / "tools/radv-link-eden.sh").read_text()
compat = (root / "headless/ps5_net_compat.c").read_text()
main = (root / "headless/main.cpp").read_text()

assert "YUZU_BUNDLED_OPENSSL=1" in cmake
assert "materialize-openssl-cert.py" in build
assert ".patch/openssl/0001-add-bundled-cert.patch" in build
assert "inline constexpr char kCert[]" in materialize
assert 'count < 100' in materialize
assert "Prospero.Eden-Encore/1" in patch
assert 'request.headers.emplace("User-Agent"' in patch
assert "BEGIN CERTIFICATE" not in patch
assert "eden-ps5-net-user-agent.patch" in apply
# Mihawk's RADV recipe intentionally redirects host DNS to an EAI_FAIL stub.
# Native-title SDK resolver imports can also point at libScePosixForWebKit and jump to 0.
# Encore therefore owns host DNS explicitly through sceNetResolver, while the link recipe
# strips Mihawk's defsym redirects and the fcntl wrapper provides SO_NBIO on sockets.
assert "ps5_net_compat.c" in cmake and "--wrap=fcntl" in cmake
assert "int __wrap_fcntl(" in compat and "EDEN_PS5_SO_NBIO = 0x1200" in compat
for needle in ("int getaddrinfo(", "void freeaddrinfo(", "const char *gai_strerror(",
               "struct hostent *gethostbyname(", "return &host;",
               "sceNetResolverCreate", "sceNetResolverStartNtoa", "sceNetPoolCreate"):
    assert needle in compat, needle
assert "set_socket_options" not in patch and "ps5_nonblocking = 0x1200" not in patch
for redirected in ("--defsym=getaddrinfo=ps5_getaddrinfo",
                   "--defsym=freeaddrinfo=ps5_freeaddrinfo",
                   "--defsym=gai_strerror=ps5_gai_strerror"):
    assert redirected in link, redirected
native_link = (root / "tools/link-headless-native.sh").read_text()
assert '"$sdk/target/lib/libc.a"' in native_link
# CMake passes a custom link script, so a target_link_options declaration alone
# does not prove that the native two-pass lld invocation wraps fcntl.
assert '--wrap=malloc_usable_size --wrap=fcntl' in native_link
assert 'link_native "$weak_scan" "$weak_map"' in native_link
assert 'link_native "$output" "$output.map"' in native_link
assert "httplib::to_string(result.error())" in patch
assert 'extern "C" int sceNetInit();' in main
assert 'const int host_net_result = sceNetInit();' in main
assert 'host network init result=%d' in main
print("Encore PS5 HTTPS/Nlib CA + DNS/socket/native-network contract PASS")
