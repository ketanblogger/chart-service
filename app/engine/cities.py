"""City list for the place-of-birth dropdown (no geocoding API in the MVP).

Coordinates are city centres in decimal degrees (north / east positive), taken from
GeoNames (CC BY 4.0) and cross-checked by hand; Miraj and Ahilyanagar were added manually.
All of India is on a single timezone.
"""

TIMEZONE = "Asia/Kolkata"

# (name, state, lat, lon) - Maharashtra and neighbours first, then the rest of India.
_CITIES = [
    ("Mumbai", "Maharashtra", 19.0728, 72.8826),
    ("Pune", "Maharashtra", 18.5196, 73.8554),
    ("Nagpur", "Maharashtra", 21.1463, 79.0849),
    ("Nashik", "Maharashtra", 19.9973, 73.7910),
    ("Thane", "Maharashtra", 19.1970, 72.9635),
    ("Navi Mumbai", "Maharashtra", 19.0368, 73.0158),
    ("Kalyan", "Maharashtra", 19.2437, 73.1355),
    ("Pimpri-Chinchwad", "Maharashtra", 18.6229, 73.8070),
    ("Chhatrapati Sambhajinagar (Aurangabad)", "Maharashtra", 19.8776, 75.3423),
    ("Solapur", "Maharashtra", 17.6715, 75.9104),
    ("Kolhapur", "Maharashtra", 16.6956, 74.2317),
    ("Sangli", "Maharashtra", 16.8544, 74.5642),
    ("Miraj", "Maharashtra", 16.8300, 74.6500),
    ("Ichalkaranji", "Maharashtra", 16.6912, 74.4605),
    ("Satara", "Maharashtra", 17.6859, 73.9933),
    ("Karad", "Maharashtra", 17.2894, 74.1818),
    ("Ahilyanagar (Ahmednagar)", "Maharashtra", 19.0948, 74.7480),
    ("Jalgaon", "Maharashtra", 21.0029, 75.5660),
    ("Dhule", "Maharashtra", 20.9013, 74.7774),
    ("Nanded", "Maharashtra", 19.1602, 77.3150),
    ("Latur", "Maharashtra", 18.3972, 76.5678),
    ("Akola", "Maharashtra", 20.7096, 76.9981),
    ("Amravati", "Maharashtra", 20.9333, 77.7500),
    ("Ratnagiri", "Maharashtra", 16.9915, 73.3102),
    ("Chandrapur", "Maharashtra", 19.9508, 79.2952),
    ("Parbhani", "Maharashtra", 19.2686, 76.7708),
    ("Beed", "Maharashtra", 18.9892, 75.7563),
    ("Pandharpur", "Maharashtra", 17.6792, 75.3310),
    ("Baramati", "Maharashtra", 18.1517, 74.5777),
    ("Panaji", "Goa", 15.4957, 73.8262),
    ("Belagavi (Belgaum)", "Karnataka", 15.8521, 74.5045),
    ("Delhi", "Delhi", 28.6519, 77.2315),
    ("Bengaluru", "Karnataka", 12.9719, 77.5937),
    ("Hyderabad", "Telangana", 17.3840, 78.4564),
    ("Chennai", "Tamil Nadu", 13.0878, 80.2785),
    ("Kolkata", "West Bengal", 22.5626, 88.3630),
    ("Ahmedabad", "Gujarat", 23.0258, 72.5873),
    ("Surat", "Gujarat", 21.1959, 72.8302),
    ("Jaipur", "Rajasthan", 26.9196, 75.7878),
    ("Lucknow", "Uttar Pradesh", 26.8393, 80.9231),
    ("Kanpur", "Uttar Pradesh", 26.4652, 80.3498),
    ("Indore", "Madhya Pradesh", 22.7179, 75.8333),
    ("Bhopal", "Madhya Pradesh", 23.2547, 77.4029),
    ("Patna", "Bihar", 25.5941, 85.1356),
    ("Vadodara", "Gujarat", 22.2994, 73.2081),
    ("Ghaziabad", "Uttar Pradesh", 28.6654, 77.4391),
    ("Ludhiana", "Punjab", 30.9120, 75.8538),
    ("Agra", "Uttar Pradesh", 27.1833, 78.0167),
    ("Varanasi", "Uttar Pradesh", 25.3167, 83.0104),
    ("Meerut", "Uttar Pradesh", 28.9800, 77.7064),
    ("Rajkot", "Gujarat", 22.2916, 70.7932),
    ("Srinagar", "Jammu and Kashmir", 34.0857, 74.8055),
    ("Amritsar", "Punjab", 31.6223, 74.8753),
    ("Prayagraj (Allahabad)", "Uttar Pradesh", 25.4448, 81.8432),
    ("Ranchi", "Jharkhand", 23.3432, 85.3094),
    ("Howrah", "West Bengal", 22.5769, 88.3186),
    ("Coimbatore", "Tamil Nadu", 11.0055, 76.9661),
    ("Jabalpur", "Madhya Pradesh", 23.1670, 79.9501),
    ("Gwalior", "Madhya Pradesh", 26.2298, 78.1734),
    ("Vijayawada", "Andhra Pradesh", 16.5074, 80.6466),
    ("Jodhpur", "Rajasthan", 26.2684, 73.0059),
    ("Madurai", "Tamil Nadu", 9.9190, 78.1195),
    ("Raipur", "Chhattisgarh", 21.2333, 81.6333),
    ("Kota", "Rajasthan", 25.1825, 75.8391),
    ("Guwahati", "Assam", 26.1844, 91.7458),
    ("Chandigarh", "Chandigarh", 30.7363, 76.7884),
    ("Hubballi (Hubli)", "Karnataka", 15.3478, 75.1338),
    ("Mysuru (Mysore)", "Karnataka", 12.2979, 76.6393),
    ("Tiruchirappalli", "Tamil Nadu", 10.8155, 78.6965),
    ("Bareilly", "Uttar Pradesh", 28.3668, 79.4317),
    ("Aligarh", "Uttar Pradesh", 27.8815, 78.0746),
    ("Moradabad", "Uttar Pradesh", 28.8389, 78.7768),
    ("Jalandhar", "Punjab", 31.3256, 75.5792),
    ("Bhubaneswar", "Odisha", 20.2724, 85.8338),
    ("Salem", "Tamil Nadu", 11.6538, 78.1554),
    ("Warangal", "Telangana", 18.0000, 79.5833),
    ("Guntur", "Andhra Pradesh", 16.2997, 80.4573),
    ("Gorakhpur", "Uttar Pradesh", 26.7663, 83.3689),
    ("Bikaner", "Rajasthan", 28.0176, 73.3149),
    ("Noida", "Uttar Pradesh", 28.5800, 77.3300),
    ("Jamshedpur", "Jharkhand", 22.8028, 86.1855),
    ("Bhilai", "Chhattisgarh", 21.2092, 81.4285),
    ("Cuttack", "Odisha", 20.4650, 85.8793),
    ("Kochi", "Kerala", 9.9399, 76.2602),
    ("Thiruvananthapuram", "Kerala", 8.4855, 76.9492),
    ("Kozhikode", "Kerala", 11.2480, 75.7804),
    ("Dehradun", "Uttarakhand", 30.3244, 78.0339),
    ("Durgapur", "West Bengal", 23.5158, 87.3080),
    ("Asansol", "West Bengal", 23.6833, 86.9833),
    ("Ajmer", "Rajasthan", 26.4521, 74.6387),
    ("Ujjain", "Madhya Pradesh", 23.1824, 75.7764),
    ("Jamnagar", "Gujarat", 22.4729, 70.0667),
    ("Siliguri", "West Bengal", 26.7100, 88.4285),
    ("Jhansi", "Uttar Pradesh", 25.4589, 78.5799),
    ("Jammu", "Jammu and Kashmir", 32.7353, 74.8617),
    ("Mangaluru (Mangalore)", "Karnataka", 12.9172, 74.8560),
    ("Udaipur", "Rajasthan", 24.5858, 73.7135),
    ("Gurugram (Gurgaon)", "Haryana", 28.4601, 77.0263),
    ("Faridabad", "Haryana", 28.4112, 77.3132),
    ("Visakhapatnam", "Andhra Pradesh", 17.7331, 83.3162),
    ("Nellore", "Andhra Pradesh", 14.4499, 79.9870),
    ("Tirupati", "Andhra Pradesh", 13.6355, 79.4199),
    ("Shimla", "Himachal Pradesh", 31.1044, 77.1666),
    ("Haridwar", "Uttarakhand", 29.9479, 78.1603),
    ("Mathura", "Uttar Pradesh", 27.5035, 77.6722),
    ("Puducherry", "Puducherry", 11.9338, 79.8298),
    ("Imphal", "Manipur", 24.8081, 93.9442),
    ("Shillong", "Meghalaya", 25.5689, 91.8831),
    ("Agartala", "Tripura", 23.8361, 91.2794),
    ("Gangtok", "Sikkim", 27.3257, 88.6122),
    ("Dhanbad", "Jharkhand", 23.7976, 86.4299),
    ("Bhavnagar", "Gujarat", 21.7629, 72.1533),
    ("Gaya", "Bihar", 24.7969, 85.0038),
    ("Vasai-Virar", "Maharashtra", 19.4559, 72.8114),
    ("Davanagere", "Karnataka", 14.4669, 75.9269),
    ("Kalaburagi (Gulbarga)", "Karnataka", 17.3358, 76.8376),
    ("Vijayapura (Bijapur)", "Karnataka", 16.8244, 75.7154),
    ("Bhagalpur", "Bihar", 25.2445, 86.9718),
    ("Muzaffarpur", "Bihar", 26.1226, 85.3906),
    ("Thrissur", "Kerala", 10.5167, 76.2167),
    ("Tirunelveli", "Tamil Nadu", 8.7274, 77.6838),
    ("Ayodhya", "Uttar Pradesh", 26.7991, 82.2047),
    ("Dwarka", "Gujarat", 22.2394, 68.9678),
    ("Shirdi", "Maharashtra", 19.7662, 74.4774),
]

CITIES = [
    {"name": name, "state": state, "lat": lat, "lon": lon, "tz": TIMEZONE}
    for name, state, lat, lon in _CITIES
]


def _normalise(name: str) -> str:
    return name.strip().lower()


# "Belagavi (Belgaum)" is findable as the full label, "belagavi" or "belgaum".
_INDEX: dict[str, dict] = {}
for _city in CITIES:
    _label = _city["name"]
    _aliases = [_label] + [part.strip(" )") for part in _label.split("(")]
    for _alias in _aliases:
        _INDEX.setdefault(_normalise(_alias), _city)


def find_city(name: str) -> dict | None:
    return _INDEX.get(_normalise(name))
