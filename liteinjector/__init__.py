# Lazy imports: the host software (liteinjector.software) does not need Migen/LiteX gateware modules.

def __getattr__(name):
    if name == "LiteInjector":
        from liteinjector.core import LiteInjector
        return LiteInjector
    if name == "LiteInjectorDriver":
        from liteinjector.software.driver.injector import LiteInjectorDriver
        return LiteInjectorDriver
    raise AttributeError(f"module 'liteinjector' has no attribute '{name}'")
