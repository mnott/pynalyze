#!/usr/bin/env python3
# encoding: utf-8

"""
pynalyze: Analyze Python files for unused functions and imports.

This script analyzes Python source files to find unused functions and imports,
ignoring functions that have decorators.

# Usage

To analyze a Python file, use the following command:

```bash
./pynalyze.py analyze <python_file>
```
"""

import ast
import typer
from rich.console import Console
from typing import Dict, NamedTuple

class ImportInfo(NamedTuple):
    module: str
    lineno: int
    is_from: bool

class FunctionInfo(NamedTuple):
    name: str
    lineno: int

# Initialize Typer app
app = typer.Typer(
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
    help="analyze: Find unused functions and imports in Python files.",
    epilog="To get help about the script, call it with the --help option."
)

console = Console()

class CodeVisitor(ast.NodeVisitor):
    def __init__(self):
        # Function tracking
        self.defined_funcs = {}  # name -> FunctionInfo
        self.called_funcs = set()
        self.decorated_funcs = set()

        # Import tracking
        self.imports = {}  # name -> ImportInfo
        self.import_froms = {}  # name -> ImportInfo
        self.used_names = set()

        # Track class context
        self.in_class = False
        self.current_class = None

    def visit_Import(self, node):
        """Track regular imports like 'import foo'"""
        for alias in node.names:
            name = alias.asname or alias.name
            self.imports[name] = ImportInfo(
                module=alias.name,
                lineno=node.lineno,
                is_from=False
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Track from imports like 'from foo import bar'"""
        module = node.module or ''
        for alias in node.names:
            name = alias.asname or alias.name
            if name != '*':
                self.import_froms[name] = ImportInfo(
                    module=module,
                    lineno=node.lineno,
                    is_from=True
                )
        self.generic_visit(node)

    def visit_Name(self, node):
        """Track any name that is used"""
        self.used_names.add(node.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        # Skip methods defined in classes - they might be used externally
        if self.in_class:
            self.generic_visit(node)
            return

        # For decorated functions, still visit the body to track used names
        if node.decorator_list:
            self.decorated_funcs.add(node.name)
            self.generic_visit(node)
            return

        self.defined_funcs[node.name] = FunctionInfo(
            name=node.name,
            lineno=node.lineno
        )
        self.generic_visit(node)

    def visit_Call(self, node):
        # Track direct function calls
        if isinstance(node.func, ast.Name):
            self.called_funcs.add(node.func.id)
        # Track method calls through self
        elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == 'self':
                self.called_funcs.add(node.func.attr)
        self.generic_visit(node)

    def visit_Attribute(self, node):
        """Track attribute access, including through self"""
        if isinstance(node.value, ast.Name):
            if node.value.id == 'self':
                # Track access to self attributes as they might be methods
                self.called_funcs.add(node.attr)
            self.used_names.add(node.value.id)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        """Handle class definitions"""
        old_class = self.current_class
        old_in_class = self.in_class
        self.current_class = node.name
        self.in_class = True
        self.generic_visit(node)
        self.current_class = old_class
        self.in_class = old_in_class

    def get_unused_imports(self) -> Dict[str, ImportInfo]:
        """Returns a dict of unused imports with their info"""
        unused = {}

        # Check regular imports
        for name, info in self.imports.items():
            if name not in self.used_names:
                unused[name] = info

        # Check from imports
        for name, info in self.import_froms.items():
            if name not in self.used_names:
                unused[name] = info

        return unused

    def get_unused_functions(self) -> Dict[str, FunctionInfo]:
        """Returns a dict of unused functions with their info"""
        unused = {}
        for name, info in self.defined_funcs.items():
            if name not in self.called_funcs and name not in self.decorated_funcs:
                unused[name] = info
        return unused

@app.command()
def analyze(
    python_file: str,
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Only show unused names"),
    no_imports: bool = typer.Option(False, "--no-imports", help="Don't check for unused imports"),
    no_functions: bool = typer.Option(False, "--no-functions", help="Don't check for unused functions")
):
    """
    Analyze a Python file for unused functions and imports.

    Args:
        python_file (str): Path to the Python file to analyze.
        quiet (bool): If True, only output the unused names.
        no_imports (bool): If True, skip checking for unused imports.
        no_functions (bool): If True, skip checking for unused functions.
    """
    try:
        # Read the file
        with open(python_file, 'r') as file:
            tree = ast.parse(file.read())

        # Find functions and imports
        visitor = CodeVisitor()
        visitor.visit(tree)

        has_issues = False

        # Handle unused functions
        if not no_functions:
            unused_funcs = visitor.get_unused_functions()
            if unused_funcs:
                has_issues = True
                if not quiet:
                    console.print(f"\n[yellow]Found {len(unused_funcs)} unused functions in {python_file}:[/yellow]")
                for name, info in sorted(unused_funcs.items(), key=lambda x: x[1].lineno):
                    if quiet:
                        print(f"func:{python_file}:{info.lineno}:{name}")
                    else:
                        console.print(f"[red]- {name} (line {info.lineno})[/red]")

        # Handle unused imports
        if not no_imports:
            unused_imports = visitor.get_unused_imports()
            if unused_imports:
                has_issues = True
                if not quiet:
                    console.print(f"\n[yellow]Found {len(unused_imports)} unused imports in {python_file}:[/yellow]")
                for name, info in sorted(unused_imports.items(), key=lambda x: x[1].lineno):
                    import_str = f"from {info.module}" if info.is_from else info.module
                    if quiet:
                        print(f"import:{python_file}:{info.lineno}:{name}")
                    else:
                        console.print(f"[red]- {name} ({import_str}, line {info.lineno})[/red]")

        if not has_issues and not quiet:
            console.print(f"[green]No unused functions or imports found in {python_file}![/green]")

    except FileNotFoundError:
        console.print(f"[red]Error: File '{python_file}' not found.[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error analyzing file: {str(e)}[/red]")
        raise typer.Exit(1)

#
# Command: Doc
#
@app.command()
def doc (
    ctx:        typer.Context,
    title:      str  = typer.Option(None,   help="The title of the document"),
    toc:        bool = typer.Option(False,  help="Whether to create a table of contents"),
) -> None:
    """
    Re-create the documentation and write it to the output file.
    """
    import importlib
    import sys
    import os
    import doc2md

    def import_path(path):
        module_name = os.path.basename(path).replace("-", "_")
        spec = importlib.util.spec_from_loader(
            module_name,
            importlib.machinery.SourceFileLoader(module_name, path),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[module_name] = module
        return module

    mod_name = os.path.basename(__file__)
    if mod_name.endswith(".py"):
        mod_name = mod_name.rsplit(".py", 1)[0]
    atitle = title or mod_name.replace("_", "-")
    module = import_path(__file__)
    docstr = module.__doc__
    result = doc2md.doc2md(docstr, atitle, toc=toc, min_level=0)
    print(result)



#
# Main function
#
if __name__ == "__main__":
    import sys
    from typer.main import get_command,get_command_name
    if len(sys.argv) == 1 or sys.argv[1] not in [get_command_name(key) for key in get_command(app).commands.keys()]:
        sys.argv.insert(1, "analyze")
    app()
