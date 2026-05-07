import importlib
import inspect
import pkgutil
from pathlib import Path

TOOLS = []

package_dir = Path(__file__).parent
package_name = __name__

for module_info in pkgutil.iter_modules([str(package_dir)]):
    module_name = module_info.name

    if module_name.startswith("_"):
        continue

    module = importlib.import_module(f"{package_name}.{module_name}")

    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__ != module.__name__:
            continue

        if obj.__name__.endswith("Tool"):
            try:
                TOOLS.append(obj())
                print(f"Loaded tool: {obj.__name__}")
            except Exception as e:
                print(f"Failed loading {obj.__name__}: {e}")