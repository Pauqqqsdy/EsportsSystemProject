from django.contrib.auth.password_validation import UserAttributeSimilarityValidator, MinimumLengthValidator, CommonPasswordValidator, NumericPasswordValidator
from django.core.exceptions import ValidationError

class CombinedPasswordValidator:
    def validate(self, password, user=None):
        validators = [
            UserAttributeSimilarityValidator(),
            MinimumLengthValidator(),
            CommonPasswordValidator(),
            NumericPasswordValidator(),
        ]
        
        errors = []
        for validator in validators:
            try:
                validator.validate(password, user)
            except ValidationError as e:
                errors.extend(e.messages)
        
        if errors:
            raise ValidationError(errors)
    
    def get_help_text(self):
        return ""