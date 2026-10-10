"""A disabled optional LoRA must never require a selected or installed file."""
import folder_paths


class IunoOptionalLora:
    @classmethod
    def INPUT_TYPES(cls):
        names = folder_paths.get_filename_list('loras')
        turbo = 'minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors'
        return {'required': {
            'model': ('MODEL',),
            'lora_name': (['None', '', *names], {'default': turbo if turbo in names else 'None'}),
            'strength_model': ('FLOAT', {'default': 1.0, 'min': -20, 'max': 20, 'step': 0.01}),
            'enabled': ('BOOLEAN', {'default': False}),
        }}

    RETURN_TYPES = ('MODEL',)
    FUNCTION = 'apply'
    CATEGORY = 'IunoASC'

    @classmethod
    def VALIDATE_INPUTS(cls, lora_name):
        # Validation runs before lazy graph evaluation; validate only when used.
        return True

    def apply(self, model, lora_name, strength_model, enabled):
        if not enabled or strength_model == 0:
            return (model,)
        if lora_name in ('', 'None', None):
            raise ValueError('Additional LoRA is enabled: select a LoRA file or disable it.')
        if lora_name not in folder_paths.get_filename_list('loras'):
            raise ValueError('Selected additional LoRA is not installed.')
        from nodes import LoraLoaderModelOnly
        return LoraLoaderModelOnly().load_lora_model_only(model, lora_name, strength_model)


NODE_CLASS_MAPPINGS = {'IunoOptionalLora': IunoOptionalLora}
NODE_DISPLAY_NAME_MAPPINGS = {'IunoOptionalLora': 'Additional LoRA · IunoASC'}

WEB_DIRECTORY = './web'
