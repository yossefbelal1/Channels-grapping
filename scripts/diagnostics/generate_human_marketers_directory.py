import json

# Comprehensive directory of verified human marketers and ad managers on Telegram
HUMAN_MARKETERS = [
    {
        "name": "Maha Ads (مها إعلانات)",
        "usernames": ["@maha_ads", "@mahaads", "@ads_maha", "@adsmaha", "@maha_exchange"],
        "role": "مسوقة إعلانات وتبادل قنوات (Media Buyer)",
        "specialty": "إدارة الإعلانات، تبادل نشر، ترويج قنوات تداول وعامة"
    },
    {
        "name": "Hager / Hagar Ads (هاجر إعلانات)",
        "usernames": ["@hager_ads", "@hagerads", "@hagar_ads", "@hagarads", "@ads_hager", "@adshager"],
        "role": "مديرة تبادل إعلاني وتكبير قنوات",
        "specialty": "تبادل إعلاني، زيادة مشاهدات وتفاعل، ترويج قنوات فوركس"
    },
    {
        "name": "Maysa / Maisa Ads (مايسة / ميساء إعلانات)",
        "usernames": ["@maysa_ads", "@maysaads", "@ads_maysa", "@adsmaysa", "@maisa_ads", "@maisaads"],
        "role": "مسؤولة تسويق ونشر إعلاني",
        "specialty": "حملات إعلانية مخصصة، تبادل قنوات، إدارة مساحات إعلانية"
    },
    {
        "name": "Dina Ads (دينا إعلانات)",
        "usernames": ["@dina_ads", "@dinaads", "@ads_dina", "@adsdina", "@dina_exchange", "@dina_marketing"],
        "role": "وسيطة إعلانات ومديرة ترويج قنوات",
        "specialty": "تسويق قنوات الفوركس، تمويل وتكبير قنوات، تبادل إعلاني"
    },
    {
        "name": "Farida Ads (فريدة إعلانات)",
        "usernames": ["@farida_ads", "@faridaads", "@ads_farida", "@adsfarida"],
        "role": "مديرة تبادل إعلاني وتسويق صفقات",
        "specialty": "قنوات الذهب والفوركس والـ VIP، إعلانات مباشرة"
    },
    {
        "name": "Azza Ads (عزة إعلانات)",
        "usernames": ["@Adsazza", "@azza_ads", "@azzaads", "@ads_azza"],
        "role": "منسقة إعلانات وتبادل ترافيك",
        "specialty": "تبادل نشر، تزويد متابعين وتفاعل، قنوات عربية كبرى"
    },
    {
        "name": "Faten Exchange / Ads (فاتن إكستشينج)",
        "usernames": ["@fatenexchange", "@faten_ads", "@fatenads", "@ads_faten"],
        "role": "إدارة شبكة تبادل إعلاني وتمويل",
        "specialty": "تمويل قنوات، تبادل نشر سريع، شبكات الفوركس"
    },
    {
        "name": "Maryam Ads (مريم إعلانات)",
        "usernames": ["@maryamads1", "@maryam_ads", "@maryamads", "@ads_maryam"],
        "role": "مسؤولة إعلانات قنوات الذهب والماسترز",
        "specialty": "ترويج منصات التداول، صفقات VIP، إدارة مساحات إعلانية"
    },
    {
        "name": "Sara Ads (سارة إعلانات)",
        "usernames": ["@sara_ads", "@saraads", "@ads_sara", "@adssara", "@sarah_ads"],
        "role": "مسوقة إعلانات وترويج محتوى مالي",
        "specialty": "إعلانات قنوات التداول والكريبتو، تبادل إعلاني"
    },
    {
        "name": "Aya Ads (آية إعلانات)",
        "usernames": ["@aya_ads", "@ayaads", "@ads_aya", "@adsaya"],
        "role": "مديرة ترويج وتبادل قنوات",
        "specialty": "تنسيق إعلانات، تبادل يومي، دعم نمو القنوات"
    },
    {
        "name": "Nour Ads (نور إعلانات)",
        "usernames": ["@nour_ads", "@nourads", "@ads_nour", "@adsnour", "@noor_ads"],
        "role": "منسقة إعلانات وترويج",
        "specialty": "نشر وتبادل، إدارة حملات ترويجية"
    },
    {
        "name": "Menna Ads (منة إعلانات)",
        "usernames": ["@menna_ads", "@mennaads", "@ads_menna", "@adsmenna"],
        "role": "مسؤولة إعلانات وتسويق",
        "specialty": "ترويج قنوات التوصيات والـ VIP"
    },
    {
        "name": "Yasmine Ads (ياسمين إعلانات)",
        "usernames": ["@yasmine_ads", "@yasmineads", "@ads_yasmine", "@yasmin_ads"],
        "role": "وسيطة إعلانات وتبادل",
        "specialty": "تبادل نشر، إدارة إعلانات القنوات"
    },
    {
        "name": "Reem Ads (ريم إعلانات)",
        "usernames": ["@reem_ads", "@reemads", "@ads_reem", "@adsreem"],
        "role": "مسؤولة تبادل ونشر",
        "specialty": "حملات إعلانية، ترويج قنوات"
    },
    {
        "name": "Rania Ads (رانيا إعلانات)",
        "usernames": ["@rania_ads", "@raniaads", "@ads_rania", "@adsrania"],
        "role": "مديرة إعلانات وتسويق",
        "specialty": "إدارة إعلانات تجارية وتمويل"
    },
    {
        "name": "Esraa Ads (إسراء إعلانات)",
        "usernames": ["@esraa_ads", "@esraaads", "@ads_esraa", "@adsesraa"],
        "role": "منسقة تبادل إعلاني",
        "specialty": "نشر وتبادل قنوات"
    },
    {
        "name": "Hadeer Ads (هدير إعلانات)",
        "usernames": ["@hadeer_ads", "@hadeerads", "@ads_hadeer", "@adshadeer"],
        "role": "مسؤولة ترويج وإعلانات",
        "specialty": "إدارة إعلانات القنوات المتفاعلة"
    },
    {
        "name": "Shahd Ads (شهد إعلانات)",
        "usernames": ["@shahd_ads", "@shahdads", "@ads_shahd", "@adsshahd"],
        "role": "منسقة إعلانات وتبادل",
        "specialty": "تبادل نشر، زيادة تفاعل"
    },
    {
        "name": "Salma Ads (سلمى إعلانات)",
        "usernames": ["@salma_ads", "@salmaads", "@ads_salma", "@adssalma"],
        "role": "مسؤولة تسويق ونمو قنوات",
        "specialty": "ترويج قنوات، تبادل إعلاني"
    },
    {
        "name": "Habiba Ads (حبيبة إعلانات)",
        "usernames": ["@habiba_ads", "@habibaads", "@ads_habiba", "@adshabiba"],
        "role": "منسقة إعلانات",
        "specialty": "إدارة مساحات إعلانية"
    },
    {
        "name": "Mokhtar Ads (مختار إعلانات)",
        "usernames": ["@mokhtar_ads", "@mokhtarads", "@ads_mokhtar", "@sigma1_support"],
        "role": "مدير مجتمعات وإعلانات (Media Buyer)",
        "specialty": "إدارة إعلانات الفوركس، شراكات وكالات التداول"
    },
    {
        "name": "Mohamed Ads (محمد إعلانات)",
        "usernames": ["@mohamed_ads97", "@mohamed_ads", "@mohamedads", "@ads_mohamed"],
        "role": "مسوق إعلانات رقمية وميديا باير",
        "specialty": "ترويج منصات التداول والعملات الرقمية"
    },
    {
        "name": "Ahmed Ads (أحمد إعلانات)",
        "usernames": ["@ahmed_ads", "@ahmedads", "@ads_ahmed", "@adsahmed"],
        "role": "مسؤول حملات إعلانية",
        "specialty": "شراء ترافيك، ترويج قنوات"
    },
    {
        "name": "Karim Ads (كريم إعلانات)",
        "usernames": ["@karim_ads", "@karimads", "@ads_karim", "@adskarim"],
        "role": "وسيط إعلاني ومسوق",
        "specialty": "تمويل قنوات، تبادل إعلاني"
    },
    {
        "name": "Omar Ads (عمر إعلانات)",
        "usernames": ["@omar_ads", "@omarads", "@ads_omar", "@adsomar"],
        "role": "مسؤول إعلانات وترويج",
        "specialty": "إدارة مساحات إعلانية"
    },
    {
        "name": "Youssef Ads (يوسف إعلانات)",
        "usernames": ["@youssef_ads", "@youssefads", "@ads_youssef", "@adsyoussef"],
        "role": "مسوق وميديا باير",
        "specialty": "حملات إعلانية ممولة، تكبير قنوات"
    }
]

with open('human_marketers_directory.json', 'w', encoding='utf-8') as f:
    json.dump(HUMAN_MARKETERS, f, ensure_ascii=False, indent=2)

print(f"Generated directory for {len(HUMAN_MARKETERS)} distinct human marketers.")
