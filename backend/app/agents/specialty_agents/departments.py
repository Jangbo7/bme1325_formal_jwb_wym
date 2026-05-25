DEPARTMENTS = [
    {"code": "02", "name": "General Medicine", "key": "general_medicine"},
    {"code": "03", "name": "Internal Medicine", "key": "internal_medicine"},
    {"code": "04", "name": "Surgery", "key": "surgery"},
    {"code": "05", "name": "OB-GYN", "key": "ob_gyn"},
    {"code": "07", "name": "Pediatrics", "key": "pediatrics"},
    {"code": "10", "name": "Ophthalmology", "key": "ophthalmology"},
    {"code": "11", "name": "ENT", "key": "ent"},
    {"code": "12", "name": "Dentistry", "key": "dentistry"},
    {"code": "13", "name": "Dermatology", "key": "dermatology"},
    {"code": "15", "name": "Psychiatry", "key": "psychiatry"},
    {"code": "21", "name": "Rehabilitation", "key": "rehabilitation"},
    {"code": "27", "name": "Pain Medicine", "key": "pain_medicine"},
]

ALLOWED_DEPARTMENT_KEYS = {item["key"] for item in DEPARTMENTS}
