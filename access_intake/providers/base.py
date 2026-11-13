"""Provider failures expose codes, never raw HTTP bodies or credentials."""
class ProviderError(RuntimeError):
    def __init__(self,code):
        self.code=code
        super().__init__('provider request failed')
