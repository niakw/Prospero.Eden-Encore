#!/usr/bin/env bash
# Source after setting root to the Eden port. Keep the qualified Eden heap;
# reuse the pinned RADV platform recipe for threads, libc, TLS and unwinding.
eden_radv_link_recipe() {
    local archive=$1
    local reference="$root/../mihawk-vulkan-review"
    local radv_sdk="$reference/.deps/native/ps5-payload-sdk"
    source "$reference/tools/radv-link.sh"
    local recipe_error="" recipe_status=0
    local recipe_error_file
    recipe_error_file=$(mktemp "${TMPDIR:-/tmp}/encore-radv-link.XXXXXX")
    radv_link_recipe "$reference" "$radv_sdk" "$archive" 2>"$recipe_error_file" || recipe_status=$?
    recipe_error=$(cat "$recipe_error_file")
    rm -f "$recipe_error_file"

    # Mihawk's standalone recipe gets compiler-rt builtins from the host
    # Clang resource dir. Homebrew LLVM on macOS does not ship the Linux
    # x86_64 archive. Encore already compiles compiler-rt emutls.c into
    # libcommon.a; keep every real recipe input but drop only that absent
    # host-only archive. This must run even when the upstream recipe filled
    # radv_link_inputs before returning its missing-input status.
    local filtered=()
    local recipe_input
    local skipped_host_builtins=0
    for recipe_input in "${radv_link_inputs[@]}"; do
        if [[ $recipe_input == */lib/linux/libclang_rt.builtins-x86_64.a && ! -f $recipe_input ]]; then
            skipped_host_builtins=1
            continue
        fi
        filtered+=("$recipe_input")
    done
    radv_link_inputs=("${filtered[@]}")

    if [[ $recipe_status -ne 0 ]]; then
        if [[ $recipe_status -ne 2 || $skipped_host_builtins -ne 1 ||
              $recipe_error != missing\ */lib/linux/libclang_rt.builtins-x86_64.a ]]; then
            [[ -n $recipe_error ]] && printf '%s\n' "$recipe_error" >&2
            return "$recipe_status"
        fi
    fi
    # The Eden linker already groups all native archives. lld rejects nested
    # groups, so flatten only the recipe's group delimiters.
    local input
    local inputs=()
    for input in "${radv_link_inputs[@]}"; do
        case "$input" in --start-group|--end-group) ;; *) inputs+=("$input") ;; esac
    done
    radv_link_inputs=("${inputs[@]}")
    local flag
    local retained=()
    for flag in "${radv_link_flags[@]}"; do
        case "$flag" in
            --wrap=malloc|--wrap=calloc|--wrap=realloc|--wrap=free|\
            --wrap=posix_memalign|--wrap=aligned_alloc|--wrap=memalign|\
            --wrap=malloc_usable_size|--wrap=reallocf|--wrap=reallocarray|\
            --wrap=getline|--wrap=getdelim) ;;
            # Mihawk's standalone RADV platform binds host DNS to EAI_FAIL stubs.
            # Encore instead compiles its own sceNetResolver-backed getaddrinfo shim;
            # the SDK libc resolver import may point at an unloaded WebKit module.
            --defsym=getaddrinfo=ps5_getaddrinfo|--defsym=freeaddrinfo=ps5_freeaddrinfo|\
            --defsym=gai_strerror=ps5_gai_strerror|--defsym=gethostbyname=ps5_gethostbyname|\
            --defsym=gethostbyname_r=ps5_gethostbyname_r|--defsym=getnameinfo=ps5_getnameinfo) ;;
            *) retained+=("$flag") ;;
        esac
    done
    # The static Mesa ICD exports radv_GetInstanceProcAddr. Eden's existing
    # static loader uses the standard public name.
    radv_link_flags=("${retained[@]}" --defsym=vkGetInstanceProcAddr=radv_GetInstanceProcAddr
        --undefined=__real_fclose --undefined=__real_fflush)
}
