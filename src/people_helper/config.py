"""Constants and configuration for People Helper."""

GITHUB_API = "https://api.github.com"

LANG_BY_EXT = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", "vendor",
    "dist", "build", ".next", "target", ".venv", "venv",
    "env", ".env", ".tox", ".mypy_cache", ".pytest_cache",
}

SKIP_EXTS = {
    ".lock", ".log", ".png", ".jpg", ".jpeg", ".gif",
    ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot",
    ".mp4", ".mp3", ".zip", ".tar", ".gz", ".pdf", ".bin",
    ".pyc", ".pyo", ".class", ".o", ".so", ".dll",
}

UTILITY_PATTERNS = [
    "util", "helper", "common", "lib", "tool", "format",
    "parse", "convert", "validate", "sanitize", "protection",
    "guard", "filter", "normaliz", "middleware", "interceptor",
    "serializer", "transformer", "adapter", "resolver", "builder",
]

FRAMEWORK_ENTRY_NAMES = {
    "route", "page", "layout", "loading", "error", "not-found",
    "middleware", "index", "main", "app", "server",
    "_app", "_document", "head", "template",
}

FRAMEWORK_SPECIAL_FILES = {
    "route.ts", "route.tsx", "route.js", "route.jsx",
    "page.tsx", "page.jsx", "page.ts", "page.js",
    "layout.tsx", "layout.ts", "layout.jsx", "layout.js",
    "loading.tsx", "loading.ts", "loading.jsx", "loading.js",
    "error.tsx", "error.ts", "error.jsx", "error.js",
    "not-found.tsx", "not-found.ts", "middleware.ts", "middleware.js",
    "_app.tsx", "_app.jsx", "_document.tsx", "_document.jsx",
    "+page.svelte", "+layout.svelte", "+server.ts",
}

FRAMEWORK_DIRS = {"app", "pages", "routes"}

EXTERNAL_SCOPES = {"types", "angular", "vue", "react", "nestjs", "prisma", "next", "svelte", "nuxt", "astro"}

# Scoring weights
CODE_QUALITY_WEIGHT = 0.5
UNIQUENESS_WEIGHT = 0.3
DEMAND_SIGNAL_WEIGHT = 0.2

# Ship effort thresholds (LOC -> hours)
SHIP_EFFORT_BRACKETS = [
    (50, 1.5),
    (150, 3.0),
    (300, 6.0),
    (500, 16.0),
]
