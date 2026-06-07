#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════
#  Workflow Determinista — PyInstaller Build Script
#  Converts the Python project into a single standalone executable.
#
#  Usage:
#    ./build_pyinstaller.sh            # Build with confirmation prompts
#    ./build_pyinstaller.sh --clean    # Clean build (removes old artifacts)
#
#  Requirements:
#    pip install pyinstaller
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────
APP_NAME="WorkflowDeterminista"
APP_VERSION="1.0.0"
COMPANY_NAME="Workflow Determinista"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_DIR/dist"
SPEC_DIR="$PROJECT_DIR/build"
ENTRY_POINT="$PROJECT_DIR/src/main.py"
VERSION_FILE="$SPEC_DIR/version_info.txt"

# ── Parse arguments ───────────────────────────────────────────────────────
CLEAN_BUILD=false
NO_CONFIRM=""

for arg in "$@"; do
    case "$arg" in
        --clean)
            CLEAN_BUILD=true
            ;;
        --noconfirm)
            NO_CONFIRM="--noconfirm"
            ;;
        --help|-h)
            echo "Usage: $0 [--clean] [--noconfirm] [--help]"
            echo ""
            echo "  --clean      Remove build/ and dist/ before building"
            echo "  --noconfirm  Pass --noconfirm to PyInstaller (overwrite without asking)"
            echo "  --help       Show this help message"
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
echo "║  PyInstaller Build — ${APP_NAME} v${APP_VERSION}"
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
    rm -rf "$BUILD_DIR" "$SPEC_DIR"
    echo "   Removed: $BUILD_DIR"
    echo "   Removed: $SPEC_DIR"
    echo ""
fi

# ── Ensure build directories exist ────────────────────────────────────────
mkdir -p "$BUILD_DIR" "$SPEC_DIR"

# ── Generate version info file (Windows) ──────────────────────────────────
# PyInstaller on Windows can embed version info into the .exe
echo "📝 Generating version info file..."
cat > "$VERSION_FILE" <<EOF
# UTF-8
#
# More details about version_info:
# https://docs.microsoft.com/en-us/windows/win32/msi/version
#
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(${APP_VERSION//./, },0),
    prodvers=(${APP_VERSION//./, },0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'${COMPANY_NAME}'),
        StringStruct(u'FileDescription', u'${APP_NAME} - Workflow Automation Engine'),
        StringStruct(u'FileVersion', u'${APP_VERSION}.0'),
        StringStruct(u'InternalName', u'${APP_NAME}'),
        StringStruct(u'LegalCopyright', u'© $(date +%Y) ${COMPANY_NAME}'),
        StringStruct(u'OriginalFilename', u'${APP_NAME}.exe'),
        StringStruct(u'ProductName', u'${APP_NAME}'),
        StringStruct(u'ProductVersion', u'${APP_VERSION}.0')])
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
EOF
echo "   Written: $VERSION_FILE"
echo ""

# ── Check PyInstaller availability ────────────────────────────────────────
echo "🔍 Checking PyInstaller..."
if ! command -v pyinstaller &> /dev/null; then
    echo "⚠️  PyInstaller not found. Installing..."
    pip install pyinstaller
fi
PYINSTALLER_VER=$(pyinstaller --version 2>/dev/null || echo "unknown")
echo "   PyInstaller version: $PYINSTALLER_VER"
echo ""

# ── Build ─────────────────────────────────────────────────────────────────
echo "🔨 Starting PyInstaller build..."
echo "─────────────────────────────────────────────────────────────"

cd "$PROJECT_DIR"

# Build the PyInstaller command
PYI_CMD="pyinstaller --onefile --windowed"
PYI_CMD+=" --name \"${APP_NAME}_v${APP_VERSION}\""

# Add data files (templates and static) — cross-platform separator
if [ "$(uname)" = "Linux" ]; then
    DATA_SEP=":"
else
    DATA_SEP=";"
fi

PYI_CMD+=" --add-data \"src/web/templates${DATA_SEP}templates\""
PYI_CMD+=" --add-data \"src/web/static${DATA_SEP}static\""

# Add version info (Windows only)
if [ "$(uname)" = "Windows" ] || [ "$(uname -o 2>/dev/null)" = "Msys" ]; then
    PYI_CMD+=" --version-file \"$VERSION_FILE\""
fi

# Icon support — uncomment and set the correct path when you have an icon
# PYI_CMD+=" --icon \"installer/icon.ico\""
# For Linux/macOS, you can also use .png with:
# PYI_CMD+=" --icon \"installer/icon.png\""

# Add --noconfirm if requested
if [ -n "$NO_CONFIRM" ]; then
    PYI_CMD+=" --noconfirm"
fi

# Clean build flag
if [ "$CLEAN_BUILD" = true ]; then
    PYI_CMD+=" --clean"
fi

# Spec file output location
PYI_CMD+=" --distpath \"$BUILD_DIR\""
PYI_CMD+=" --workpath \"$SPEC_DIR\""
PYI_CMD+=" --specpath \"$SPEC_DIR\""

# Entry point
PYI_CMD+=" \"$ENTRY_POINT\""

echo "   Command: $PYI_CMD"
echo ""

eval $PYI_CMD

# ── Post-build verification ───────────────────────────────────────────────
echo ""
echo "─────────────────────────────────────────────────────────────"
echo "🔍 Post-build verification..."

# Determine the expected output file
if [ "$(uname)" = "Windows" ] || [ "$(uname -o 2>/dev/null)" = "Msys" ]; then
    EXPECTED_FILE="$BUILD_DIR/${APP_NAME}_v${APP_VERSION}.exe"
else
    EXPECTED_FILE="$BUILD_DIR/${APP_NAME}_v${APP_VERSION}"
fi

if [ -f "$EXPECTED_FILE" ]; then
    FILE_SIZE=$(du -h "$EXPECTED_FILE" | cut -f1)
    echo "✅ Build successful!"
    echo "   Output  : $EXPECTED_FILE"
    echo "   Size    : $FILE_SIZE"
else
    echo "❌ Build FAILED — expected output not found: $EXPECTED_FILE"
    echo "   Check the build log above for errors."
    exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Build complete: $EXPECTED_FILE"
echo "═══════════════════════════════════════════════════════════"
