#!/bin/bash
#
# Build release archive for agents
#
# Usage: ./scripts/build-release.sh [VERSION] [--force]
#
# Creates versioned release in releases/ directory.
# Appends release info with SHA256 to CHANGELOG.md
# Previous releases are preserved, not deleted.
#
# Options:
#   --force    Overwrite existing release without prompting
#

set -euo pipefail

# Platform-portable SHA256 function
sha256() {
    if command -v sha256sum &> /dev/null; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum &> /dev/null; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        echo "Error: Neither sha256sum nor shasum found" >&2
        exit 1
    fi
}

# Check required commands
check_requirements() {
    local missing=()

    if ! command -v tar &> /dev/null; then
        missing+=("tar")
    fi

    if ! command -v zip &> /dev/null; then
        missing+=("zip")
    fi

    if ! command -v sha256sum &> /dev/null && ! command -v shasum &> /dev/null; then
        missing+=("sha256sum or shasum")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        echo "Error: Missing required commands: ${missing[*]}"
        exit 1
    fi
}

check_requirements

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RELEASES_DIR="$PROJECT_DIR/releases"
CHANGELOG="$PROJECT_DIR/CHANGELOG.md"

# Parse arguments
FORCE=false
VERSION=""

for arg in "$@"; do
    case "$arg" in
        --force|-f)
            FORCE=true
            ;;
        --help|-h)
            echo "Usage: $0 [VERSION] [--force]"
            echo ""
            echo "Build a release archive for agents."
            echo ""
            echo "Arguments:"
            echo "  VERSION    Version to build (default: read from agents script)"
            echo "  --force    Overwrite existing release without prompting"
            exit 0
            ;;
        *)
            if [ -z "$VERSION" ]; then
                VERSION="$arg"
            fi
            ;;
    esac
done

# Get version from agents script if not provided
if [ -z "$VERSION" ]; then
    VERSION=$(grep -m1 'AGENTS_VERSION=' "$PROJECT_DIR/agents" | cut -d'"' -f2)
fi

if [ -z "$VERSION" ]; then
    echo "Error: Could not determine version"
    exit 1
fi

RELEASE_NAME="agents-${VERSION}"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_NAME"
ARCHIVE_TAR="$RELEASES_DIR/${RELEASE_NAME}.tar.gz"
ARCHIVE_ZIP="$RELEASES_DIR/${RELEASE_NAME}.zip"
CHECKSUM_FILE="$RELEASES_DIR/${RELEASE_NAME}.sha256"

echo "Building release: $VERSION"
echo

# Create releases directory
mkdir -p "$RELEASES_DIR"

# Check if release already exists
if [ -d "$RELEASE_DIR" ]; then
    echo "Warning: Release directory already exists: $RELEASE_DIR"
    if $FORCE; then
        echo "Force mode: overwriting existing release"
    elif [ -t 0 ]; then
        # Interactive terminal - prompt user
        read -p "Overwrite? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Aborted."
            exit 1
        fi
    else
        # Non-interactive - abort unless --force
        echo "Error: Release exists and running non-interactively."
        echo "Use --force to overwrite."
        exit 1
    fi
fi

# Create release directory
mkdir -p "$RELEASE_DIR"

# Copy release files
echo "Copying files to $RELEASE_DIR ..."
cp "$PROJECT_DIR/agents" "$RELEASE_DIR/"
cp "$PROJECT_DIR/agents.1.txt" "$RELEASE_DIR/"
cp "$PROJECT_DIR/install.sh" "$RELEASE_DIR/"
cp "$PROJECT_DIR/README.md" "$RELEASE_DIR/"
cp "$PROJECT_DIR/CHANGELOG.md" "$RELEASE_DIR/"
cp -r "$PROJECT_DIR/scripts" "$RELEASE_DIR/"

# Copy LICENSE if exists
if [ -f "$PROJECT_DIR/LICENSE" ]; then
    cp "$PROJECT_DIR/LICENSE" "$RELEASE_DIR/"
else
    echo "Note: No LICENSE file found (consider adding one)"
fi

# Make scripts executable
chmod +x "$RELEASE_DIR/agents"
chmod +x "$RELEASE_DIR/install.sh"

# Create archives
echo "Creating $ARCHIVE_TAR ..."
tar -czf "$ARCHIVE_TAR" -C "$RELEASES_DIR" "$RELEASE_NAME"

echo "Creating $ARCHIVE_ZIP ..."
(cd "$RELEASES_DIR" && zip -rq "${RELEASE_NAME}.zip" "$RELEASE_NAME")

# Generate checksums (using portable sha256 function)
echo "Generating checksums..."
SHA_TAR=$(sha256 "$ARCHIVE_TAR")
SHA_ZIP=$(sha256 "$ARCHIVE_ZIP")

# Save checksums to file
cat > "$CHECKSUM_FILE" << EOF
# SHA256 checksums for agents $VERSION
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")

$SHA_TAR  ${RELEASE_NAME}.tar.gz
$SHA_ZIP  ${RELEASE_NAME}.zip
EOF

# Append to CHANGELOG.md (if not already present)
if grep -q "^### Release v${VERSION} -" "$CHANGELOG" 2>/dev/null; then
    echo "Note: Release v${VERSION} already in CHANGELOG.md, skipping append"
else
    echo "Appending release info to CHANGELOG.md ..."
    RELEASE_DATE=$(date +"%Y-%m-%d %H:%M UTC")

    cat >> "$CHANGELOG" << EOF

---

### Release v${VERSION} - ${RELEASE_DATE}

| File | SHA256 |
|------|--------|
| ${RELEASE_NAME}.tar.gz | \`${SHA_TAR}\` |
| ${RELEASE_NAME}.zip | \`${SHA_ZIP}\` |
EOF
fi

# Show results
echo
echo "=========================================="
echo "  Release build complete: v$VERSION"
echo "=========================================="
echo
echo "Release directory:"
echo "  $RELEASE_DIR"
echo
echo "Archives:"
ls -lh "$ARCHIVE_TAR" "$ARCHIVE_ZIP" | awk '{print "  " $9 " (" $5 ")"}'
echo
echo "Checksums saved to:"
echo "  $CHECKSUM_FILE"
echo
echo "CHANGELOG.md updated with SHA256 hashes."
echo
echo "─────────────────────────────────────────"
echo "Next steps:"
echo "─────────────────────────────────────────"
echo
echo "1. Test the release:"
echo "   tar -xzf $ARCHIVE_TAR -C /tmp"
echo "   /tmp/$RELEASE_NAME/install.sh --dry-run"
echo
echo "2. Commit:"
echo "   git add releases/ CHANGELOG.md"
echo "   git commit -m 'Release v$VERSION'"
echo
echo "3. Tag and push:"
echo "   git tag -a v$VERSION -m 'Release $VERSION'"
echo "   git push origin main --tags"
echo
echo "4. Create GitHub Release, upload:"
echo "   - $ARCHIVE_TAR"
echo "   - $ARCHIVE_ZIP"
echo "   - $CHECKSUM_FILE"
