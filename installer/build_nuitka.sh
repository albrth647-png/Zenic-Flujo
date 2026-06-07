#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
#  Workflow Determinista — Nuitka Build Script
#  Alternative to PyInstaller — produces fewer antivirus false positives
#  and generally better-optimized binaries.
#
#  Usage:
#    ./build_nuitka.sh            # Build the project
#    ./build_nuitka.sh --clean    # Clean build (removes old artifacts)
#
#  Requirements:
#    pip install nuitka
#    On Linux: sudo apt install ccache  (optional, speeds up recompilation)
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────
APP_NAME="WorkflowDeterminista"
APP_VERSION="1.0.0"
COMPANY_NAME="Workflow Determinista"
PRODUCT_NAME="Workflow Determinista"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_DIR/dist"
ENTRY_POINT="$PROJECT_DIR/src/main.py"

# ── Parse arguments ───────────────────────────────────────────────────────
CLEAN_BUILD=false

for arg in "$@"; do
    case "$arg" in
        --clean)
            CLEAN_BUILD=true
            ;;
        --help|-h)
            echo "Usage: $0 [--clean] [--help]"
            echo ""
            echo "  --clean  Remove dist/ before building"
            echo "  --help   Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

# ── Banner ────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Nuitka Build — ${APP_NAME} v${APP_VERSION}"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Project dir : $PROJECT_DIR"
echo "  Build dir   : $BUILD_DIR"
echo "  Entry point : $ENTRY_POINT"
echo "  Clean build : $CLEAN_BUILD"
echo ""

# ── Clean if requested ────────────────────────────────────────────────────
if [ "$CLEAN_BUILD" = true ]; then
    echo "🧹 Cleaning previous build artifacts..."
    rm -rf "$BUILD_DIR"
    echo "   Removed: $BUILD_DIR"
    # Also remove Nuitka cache
    rm -rf "$PROJECT_DIR/${APP_NAME}.build" "$PROJECT_DIR/${APP_NAME}.dist"
    echo "   Removed Nuitka cache directories"
    echo ""
fi

# ── Ensure build directory exists ─────────────────────────────────────────
mkdir -p "$BUILD_DIR"

# ── Check Nuitka availability ─────────────────────────────────────────────
echo "🔍 Checking Nuitka..."
if ! python -m nuitka --version &> /dev/null; then
    echo "⚠️  Nuitka not found. Installing..."
    pip install nuitka
fi
NUITKA_VER=$(python -m nuitka --version 2>/dev/null | head -1 || echo "unknown")
echo "   Nuitka version: $NUITKA_VER"
echo ""

# ── Check for C compiler ─────────────────────────────────────────────────
echo "🔍 Checking C compiler..."
if command -v gcc &> /dev/null; then
    echo "   gcc: $(gcc --version | head -1)"
elif command -v cl &> /dev/null; then
    echo "   MSVC: $(cl 2>&1 | head -1)"
else
    echo "⚠️  WARNING: No C compiler found. Nuitka requires a C compiler."
    echo "   On Linux: sudo apt install gcc"
    echo "   On Windows: Install Visual Studio Build Tools or MinGW"
fi
echo ""

# ── Build ─────────────────────────────────────────────────────────────────
echo "🔨 Starting Nuitka build..."
echo "─────────────────────────────────────────────────────────────"

cd "$PROJECT_DIR"

# Build the Nuitka command
NUITKA_CMD="python -m nuitka"

# ── Core options ──────────────────────────────────────────────────────────
NUITKA_CMD+=" --standalone"
NUITKA_CMD+=" --onefile"
NUITKA_CMD+=" --output-dir=\"$BUILD_DIR\""

# ── Output filename ──────────────────────────────────────────────────────
NUITKA_CMD+=" --output-filename=\"${APP_NAME}\""

# ── Product metadata ─────────────────────────────────────────────────────
NUITKA_CMD+=" --product-name=\"${PRODUCT_NAME}\""
NUITKA_CMD+=" --file-version=\"${APP_VERSION}\""
NUITKA_CMD+=" --company-name=\"${COMPANY_NAME}\""

# ── Icon support — uncomment when you have an icon file ──────────────────
# For Windows:
# NUITKA_CMD+=" --windows-icon-from-ico=\"installer/icon.ico\""
# For Linux:
# NUITKA_CMD+=" --linux-icon=\"installer/icon.png\""

# ── Plugins ──────────────────────────────────────────────────────────────
# tkinter is used by the installer, NOT by the main application.
# The main app uses Flask (Jinja2 templates) so we need the anti-bloat
# plugin to avoid pulling in unnecessary packages.
NUITKA_CMD+=" --enable-plugin=anti-bloat"

# ── Data files ───────────────────────────────────────────────────────────
NUITKA_CMD+=" --include-data-dir=src/web/templates=templates"
NUITKA_CMD+=" --include-data-dir=src/web/static=static"

# ── Exclude unnecessary modules ──────────────────────────────────────────
# tkinter is only used by the installer, not the main Flask app
NUITKA_CMD+=" --nofollow-import-to=tkinter"
NUITKA_CMD+=" --nofollow-import-to=tk"
NUITKA_CMD+=" --nofollow-import-to=_tkinter"

# Exclude other heavy/unused stdlib modules to reduce binary size
NUITKA_CMD+=" --nofollow-import-to=test"
NUITKA_CMD+=" --nofollow-import-to=unittest"
NUITKA_CMD+=" --nofollow-import-to=pydoc"
NUITKA_CMD+=" --nofollow-import-to=doctest"
NUITKA_CMD+=" --nofollow-import-to=distutils"
NUITKA_CMD+=" --nofollow-import-to=setuptools"

# ── Optimization flags ───────────────────────────────────────────────────
NUITKA_CMD+=" --python-flag=no_site"
NUITKA_CMD+=" --python-flag=no_warnings"
NUITKA_CMD+=" --assume-yes-for-downloads"

# ── Windows-specific options ─────────────────────────────────────────────
if [ "$(uname)" = "Windows" ] || [ "$(uname -o 2>/dev/null)" = "Msys" ]; then
    # Disable console window on Windows (GUI mode)
    NUITKA_CMD+=" --windows-disable-console"
    # String for the Windows version info
    NUITKA_CMD+=" --windows-file-version=\"${APP_VERSION}\""
    NUITKA_CMD+=" --windows-product-version=\"${APP_VERSION}\""
    NUITKA_CMD+=" --windows-company-name=\"${COMPANY_NAME}\""
    NUITKA_CMD+=" --windows-product-name=\"${PRODUCT_NAME}\""
    NUITKA_CMD+=" --windows-file-description=\"${PRODUCT_NAME} - Workflow Automation Engine\""
fi

# ── Entry point ──────────────────────────────────────────────────────────
NUITKA_CMD+=" \"$ENTRY_POINT\""

echo "   Command: $NUITKA_CMD"
echo ""

eval $NUITKA_CMD

# ── Post-build verification ───────────────────────────────────────────────
echo ""
echo "─────────────────────────────────────────────────────────────"
echo "🔍 Post-build verification..."

# Determine the expected output file
if [ "$(uname)" = "Windows" ] || [ "$(uname -o 2>/dev/null)" = "Msys" ]; then
    EXPECTED_FILE="$BUILD_DIR/${APP_NAME}.exe"
else
    EXPECTED_FILE="$BUILD_DIR/${APP_NAME}.bin"
    # Nuitka onefile may also produce just the app name without extension
    if [ ! -f "$EXPECTED_FILE" ]; then
        EXPECTED_FILE="$BUILD_DIR/${APP_NAME}"
    fi
fi

if [ -f "$EXPECTED_FILE" ]; then
    FILE_SIZE=$(du -h "$EXPECTED_FILE" | cut -f1)
    echo "✅ Build successful!"
    echo "   Output  : $EXPECTED_FILE"
    echo "   Size    : $FILE_SIZE"

    # Test that the binary is executable (Unix only)
    if [ "$(uname)" != "Windows" ] && [ "$(uname -o 2>/dev/null)" != "Msys" ]; then
        chmod +x "$EXPECTED_FILE" 2>/dev/null || true
        if [ -x "$EXPECTED_FILE" ]; then
            echo "   Executable: Yes"
        else
            echo "   ⚠️  WARNING: Output file is not executable"
        fi
    fi
else
    echo "❌ Build FAILED — expected output not found: $EXPECTED_FILE"
    echo "   Check the build log above for errors."
    echo ""
    echo "   Listing dist/ contents:"
    ls -la "$BUILD_DIR/" 2>/dev/null || echo "   (dist/ directory is empty or missing)"
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Build complete: $EXPECTED_FILE"
echo "═══════════════════════════════════════════════════════════"
