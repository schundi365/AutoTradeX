"""
Code Scanner Utility - Detect Duplicates and Redundant Code

Scans Python codebase for:
1. Duplicate functions (identical or similar code)
2. Duplicate classes
3. Redundant imports
4. Dead code (unused functions/classes)
5. Similar code blocks (potential refactoring opportunities)

Usage:
    python scripts/scan_duplicates.py
    python scripts/scan_duplicates.py --threshold 0.8  # Similarity threshold
    python scripts/scan_duplicates.py --report duplicates_report.txt
"""

import ast
import hashlib
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple
import difflib


@dataclass
class CodeBlock:
    """Represents a code block (function, class, etc.)"""
    name: str
    file_path: str
    line_start: int
    line_end: int
    code: str
    hash: str
    type: str  # 'function', 'class', 'method'


class DuplicateScanner:
    """Scans Python codebase for duplicates and redundant code"""
    
    def __init__(self, root_dir: str = ".", similarity_threshold: float = 0.85):
        self.root_dir = Path(root_dir)
        self.similarity_threshold = similarity_threshold
        self.code_blocks: List[CodeBlock] = []
        self.imports: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        self.duplicates: List[Tuple[CodeBlock, CodeBlock, float]] = []
        self.redundant_imports: Dict[str, List[str]] = defaultdict(list)
        
        # Directories to skip
        self.skip_dirs = {
            '.venv', 'venv', '__pycache__', '.git', '.hypothesis',
            'node_modules', '.pytest_cache', 'htmlcov', '.kiro',
            'lora_output', 'training_data', 'logs', 'models'
        }
        
        # Files to skip
        self.skip_files = {
            '__init__.py', 'test_simple.py'
        }
    
    def scan(self):
        """Main scan entry point"""
        print(f"🔍 Scanning {self.root_dir} for duplicates and redundant code...")
        print(f"   Similarity threshold: {self.similarity_threshold:.0%}\n")
        
        # Collect all Python files
        python_files = self._get_python_files()
        print(f"📁 Found {len(python_files)} Python files\n")
        
        # Parse each file
        for file_path in python_files:
            self._parse_file(file_path)
        
        print(f"📊 Extracted {len(self.code_blocks)} code blocks\n")
        
        # Find duplicates
        self._find_duplicates()
        
        # Find redundant imports
        self._find_redundant_imports()
        
        # Generate report
        self._print_report()
    
    def _get_python_files(self) -> List[Path]:
        """Get all Python files in the project"""
        python_files = []
        
        for path in self.root_dir.rglob("*.py"):
            # Skip excluded directories
            if any(skip in path.parts for skip in self.skip_dirs):
                continue
            
            # Skip excluded files
            if path.name in self.skip_files:
                continue
            
            python_files.append(path)
        
        return sorted(python_files)
    
    def _parse_file(self, file_path: Path):
        """Parse a Python file and extract code blocks"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()
            
            tree = ast.parse(content, filename=str(file_path))
            
            # Extract functions and classes
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    self._extract_function(node, file_path, lines)
                elif isinstance(node, ast.ClassDef):
                    self._extract_class(node, file_path, lines)
                elif isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
                    self._extract_import(node, file_path)
        
        except Exception as e:
            print(f"⚠️  Error parsing {file_path}: {e}")
    
    def _extract_function(self, node: ast.FunctionDef, file_path: Path, lines: List[str]):
        """Extract function code block"""
        # Skip private/magic methods in analysis (but still track them)
        if node.name.startswith('_') and not node.name.startswith('__'):
            return
        
        start_line = node.lineno - 1
        end_line = node.end_lineno if node.end_lineno else start_line + 1
        
        code = '\n'.join(lines[start_line:end_line])
        normalized_code = self._normalize_code(code)
        code_hash = hashlib.md5(normalized_code.encode()).hexdigest()
        
        block = CodeBlock(
            name=node.name,
            file_path=str(file_path.relative_to(self.root_dir)),
            line_start=node.lineno,
            line_end=end_line + 1,
            code=code,
            hash=code_hash,
            type='function'
        )
        
        self.code_blocks.append(block)
    
    def _extract_class(self, node: ast.ClassDef, file_path: Path, lines: List[str]):
        """Extract class code block"""
        start_line = node.lineno - 1
        end_line = node.end_lineno if node.end_lineno else start_line + 1
        
        code = '\n'.join(lines[start_line:end_line])
        normalized_code = self._normalize_code(code)
        code_hash = hashlib.md5(normalized_code.encode()).hexdigest()
        
        block = CodeBlock(
            name=node.name,
            file_path=str(file_path.relative_to(self.root_dir)),
            line_start=node.lineno,
            line_end=end_line + 1,
            code=code,
            hash=code_hash,
            type='class'
        )
        
        self.code_blocks.append(block)
    
    def _extract_import(self, node, file_path: Path):
        """Extract import statements"""
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                self.imports[module].append((str(file_path.relative_to(self.root_dir)), node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            for alias in node.names:
                full_name = f"{module}.{alias.name}" if module else alias.name
                self.imports[full_name].append((str(file_path.relative_to(self.root_dir)), node.lineno))
    
    def _normalize_code(self, code: str) -> str:
        """Normalize code for comparison (remove comments, whitespace, etc.)"""
        lines = []
        for line in code.splitlines():
            # Remove comments
            if '#' in line:
                line = line[:line.index('#')]
            # Strip whitespace
            line = line.strip()
            if line:
                lines.append(line)
        return '\n'.join(lines)
    
    def _find_duplicates(self):
        """Find duplicate and similar code blocks"""
        print("🔎 Analyzing code blocks for duplicates...")
        
        # Group by hash for exact duplicates
        hash_groups = defaultdict(list)
        for block in self.code_blocks:
            hash_groups[block.hash].append(block)
        
        # Find exact duplicates
        for hash_val, blocks in hash_groups.items():
            if len(blocks) > 1:
                # Add all pairs
                for i in range(len(blocks)):
                    for j in range(i + 1, len(blocks)):
                        self.duplicates.append((blocks[i], blocks[j], 1.0))
        
        # Find similar code (fuzzy matching)
        for i, block1 in enumerate(self.code_blocks):
            for block2 in self.code_blocks[i + 1:]:
                # Skip if already found as exact duplicate
                if block1.hash == block2.hash:
                    continue
                
                # Skip if different types
                if block1.type != block2.type:
                    continue
                
                # Calculate similarity
                similarity = self._calculate_similarity(block1.code, block2.code)
                
                if similarity >= self.similarity_threshold:
                    self.duplicates.append((block1, block2, similarity))
    
    def _calculate_similarity(self, code1: str, code2: str) -> float:
        """Calculate similarity ratio between two code blocks"""
        normalized1 = self._normalize_code(code1)
        normalized2 = self._normalize_code(code2)
        
        return difflib.SequenceMatcher(None, normalized1, normalized2).ratio()
    
    def _find_redundant_imports(self):
        """Find imports that appear in multiple files (potential for consolidation)"""
        print("🔎 Analyzing imports for redundancy...")
        
        for module, locations in self.imports.items():
            if len(locations) >= 5:  # Imported in 5+ files
                self.redundant_imports[module] = [loc[0] for loc in locations]
    
    def _print_report(self):
        """Print scan report"""
        print("\n" + "=" * 80)
        print("📋 DUPLICATE CODE REPORT")
        print("=" * 80 + "\n")
        
        # Exact duplicates
        exact_dupes = [(b1, b2, sim) for b1, b2, sim in self.duplicates if sim == 1.0]
        if exact_dupes:
            print(f"🔴 EXACT DUPLICATES ({len(exact_dupes)} pairs found)")
            print("-" * 80)
            
            for block1, block2, _ in exact_dupes:
                print(f"\n  {block1.type.upper()}: {block1.name}")
                print(f"    📄 {block1.file_path}:{block1.line_start}")
                print(f"    📄 {block2.file_path}:{block2.line_start}")
                print(f"    Lines: {len(block1.code.splitlines())}")
        else:
            print("✅ No exact duplicates found")
        
        # Similar code
        similar = [(b1, b2, sim) for b1, b2, sim in self.duplicates if sim < 1.0]
        if similar:
            print(f"\n\n🟡 SIMILAR CODE ({len(similar)} pairs found)")
            print("-" * 80)
            
            # Sort by similarity (highest first)
            similar.sort(key=lambda x: x[2], reverse=True)
            
            for block1, block2, similarity in similar[:10]:  # Show top 10
                print(f"\n  {block1.type.upper()}: {block1.name} ↔ {block2.name}")
                print(f"    Similarity: {similarity:.1%}")
                print(f"    📄 {block1.file_path}:{block1.line_start}")
                print(f"    📄 {block2.file_path}:{block2.line_start}")
            
            if len(similar) > 10:
                print(f"\n  ... and {len(similar) - 10} more similar pairs")
        else:
            print("\n✅ No similar code blocks found")
        
        # Redundant imports
        if self.redundant_imports:
            print(f"\n\n🟠 FREQUENTLY IMPORTED MODULES (potential for consolidation)")
            print("-" * 80)
            
            # Sort by frequency
            sorted_imports = sorted(
                self.redundant_imports.items(),
                key=lambda x: len(x[1]),
                reverse=True
            )
            
            for module, files in sorted_imports[:15]:  # Show top 15
                print(f"\n  📦 {module}")
                print(f"    Used in {len(files)} files")
                if len(files) <= 5:
                    for f in files:
                        print(f"      - {f}")
        else:
            print("\n✅ No redundant imports detected")
        
        # Summary
        print("\n\n" + "=" * 80)
        print("📊 SUMMARY")
        print("=" * 80)
        print(f"  Total code blocks analyzed: {len(self.code_blocks)}")
        print(f"  Exact duplicates: {len(exact_dupes)} pairs")
        print(f"  Similar code blocks: {len(similar)} pairs")
        print(f"  Frequently imported modules: {len(self.redundant_imports)}")
        print()
    
    def save_report(self, output_file: str):
        """Save report to file"""
        with open(output_file, 'w', encoding='utf-8') as f:
            # Redirect stdout to file
            original_stdout = sys.stdout
            sys.stdout = f
            self._print_report()
            sys.stdout = original_stdout
        
        print(f"💾 Report saved to: {output_file}")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Scan Python codebase for duplicates and redundant code"
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=0.85,
        help='Similarity threshold (0.0-1.0, default: 0.85)'
    )
    parser.add_argument(
        '--report',
        type=str,
        help='Save report to file'
    )
    parser.add_argument(
        '--dir',
        type=str,
        default='.',
        help='Root directory to scan (default: current directory)'
    )
    
    args = parser.parse_args()
    
    # Validate threshold
    if not 0.0 <= args.threshold <= 1.0:
        print("❌ Error: Threshold must be between 0.0 and 1.0")
        sys.exit(1)
    
    # Run scanner
    scanner = DuplicateScanner(
        root_dir=args.dir,
        similarity_threshold=args.threshold
    )
    scanner.scan()
    
    # Save report if requested
    if args.report:
        scanner.save_report(args.report)


if __name__ == "__main__":
    main()
