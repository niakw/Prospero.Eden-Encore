#!/usr/bin/env bash
# Source after setting root to the Eden port. Keep the qualified Eden heap;
# reuse the pinned RADV platform recipe for threads, libc, TLS and unwinding.
eden_radv_link_recipe() {
    local archive=$1
    local reference="$root/../mihawk-vulkan-review"
    local radv_sdk="$reference/.deps/native/ps5-payload-sdk"
    source "$reference/tools/radv-link.sh"
    radv_link_recipe "$reference" "$radv_sdk" "$archive" || return
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
            *) retained+=("$flag") ;;
        esac
    done
    # Mesa's generated dispatch tables weak-reference every optional RADV entrypoint.
    # Whole-archive is required so real entrypoints are retained, but functions not built by this
    # RADV configuration must be NULL. Leaving those weak names unresolved makes lld expose them
    # as dynamic imports, which a PS5 native title cannot satisfy.
    local nm_tool
    nm_tool=$(command -v llvm-nm-18 || command -v llvm-nm || command -v nm)
    local -a missing_radv=()
    mapfile -t missing_radv < <(
        comm -23 \
            <("$nm_tool" --undefined-only "$archive" 2>/dev/null |
                awk '$1 ~ /^[wWvV]$/ && $2 ~ /^radv_/ {print $2}' | sort -u) \
            <("$nm_tool" --defined-only "$archive" 2>/dev/null |
                awk '$NF ~ /^radv_/ {print $NF}' | sort -u)
    )
    local name
    for name in "${missing_radv[@]}"; do
        retained+=("--defsym=${name}=0")
    done
    printf 'RADV optional entrypoints resolved to NULL: %d\n' "${#missing_radv[@]}"

    # The static Mesa ICD exports radv_GetInstanceProcAddr. Eden's existing
    # static loader uses the standard public name.
    radv_link_flags=("${retained[@]}" --defsym=vkGetInstanceProcAddr=radv_GetInstanceProcAddr
        --undefined=__real_fclose --undefined=__real_fflush)
}
