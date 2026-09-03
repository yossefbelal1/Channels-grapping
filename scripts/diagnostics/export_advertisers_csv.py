import csv
import json

# Add tamerads1 from user image
ranked_advertisers = [
    # Tier 1
    {"rank": 1, "username": "@farida_ads", "name": "Farida Ads (فريدة)", "tier": "Tier 1 (الكبرى)", "channels_count": "+25 قناة", "specialty": "إدارة وتبادل صفقات كبرى قنوات الذهب والفوركس والـ VIP"},
    {"rank": 2, "username": "@Adsazza", "name": "Azza Ads (عزة)", "tier": "Tier 1 (الكبرى)", "channels_count": "+20 قناة", "specialty": "منسقة إعلانات وتبادل ترافيك ومتابعين"},
    {"rank": 3, "username": "@fatenexchange", "name": "Faten Exchange (فاتن)", "tier": "Tier 1 (الكبرى)", "channels_count": "+18 قناة", "specialty": "إدارة شبكة تبادل إعلاني وتمويل قنوات الفوركس"},
    {"rank": 4, "username": "@adprofx", "name": "Ad Pro FX (دينا إعلانات)", "tier": "Tier 1 (الكبرى)", "channels_count": "+15 قناة", "specialty": "وكالة إعلانات وترويج قنوات التداول والفوركس"},
    {"rank": 5, "username": "@EliteTradersAd", "name": "Elite Traders Hub", "tier": "Tier 1 (الكبرى)", "channels_count": "+15 قناة", "specialty": "شبكة التبادل الإعلاني والترويج لقنوات المتداولين"},
    {"rank": 6, "username": "@Growthengine_co", "name": "Growth Engine Official", "tier": "Tier 1 (الكبرى)", "channels_count": "+15 قناة", "specialty": "وكالة نمو وتمويل وشراء ترافيك وحملات إعلانية"},
    {"rank": 7, "username": "@MaryamAds1", "name": "Maryam Ads (مريم)", "tier": "Tier 1 (الكبرى)", "channels_count": "+12 قناة", "specialty": "إدارة إعلانات وترويج شبكات الذهب والماسترز"},
    {"rank": 8, "username": "@maysa_ads", "name": "Maysa Ads (مايسة)", "tier": "Tier 1 (الكبرى)", "channels_count": "+12 قناة", "specialty": "مسؤولة تسويق ونشر إعلاني ومؤثرين وتداول"},
    {"rank": 9, "username": "@HagerAds", "name": "Hager Ads (هاجر)", "tier": "Tier 1 (الكبرى)", "channels_count": "+10 قنوات", "specialty": "مديرة تبادل إعلاني وتكبير قنوات التداول"},
    {"rank": 10, "username": "@Mohamed_ads97", "name": "Mohamed Ads 97 (محمد)", "tier": "Tier 1 (الكبرى)", "channels_count": "+10 قنوات", "specialty": "ميديا باير وتسويق منصات التداول الرقمي"},
    {"rank": 11, "username": "@protradersad", "name": "Pro Traders Exchange", "tier": "Tier 1 (الكبرى)", "channels_count": "+10 قنوات", "specialty": "ترويج وتبادل قنوات التداول والخدمات المالية"},
    {"rank": 12, "username": "@dinaads", "name": "Dina Ads (دينا)", "tier": "Tier 1 (الكبرى)", "channels_count": "+10 قنوات", "specialty": "تسويق قنوات الفوركس والتمويل الإعلاني"},

    # Tier 2
    {"rank": 13, "username": "@tamerads1", "name": "Tamer Ads (تامر)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+8 قنوات", "specialty": "إدارة إعلانات وتمويل وتكبير قنوات فوركس وتداول"},
    {"rank": 14, "username": "@ReemAds", "name": "Reem Ads (ريم)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+8 قنوات", "specialty": "إدارة حملات ترويجية وتبادل إعلاني مباشر"},
    {"rank": 15, "username": "@Emanadsa", "name": "Eman Ads (إيمان)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+8 قنوات", "specialty": "مسؤولة إعلانات قنوات واستقبال رعايات"},
    {"rank": 16, "username": "@Asmaaa_ads", "name": "Asmaa Ads (أسماء)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+8 قنوات", "specialty": "تسويق وتبادل إعلاني لقنوات الفوركس والمال"},
    {"rank": 17, "username": "@nonaads", "name": "Nona Ads (نونا / ناهد)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+8 قنوات", "specialty": "مسؤولة تبادل إعلاني وتكبير قنوات تداول"},
    {"rank": 18, "username": "@Sarah_Ads", "name": "Sarah Ads (سارة)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+8 قنوات", "specialty": "إعلانات وترويج قنوات الكريبتو والتداول"},
    {"rank": 19, "username": "@ADSSALMAa", "name": "Salma Ads (سلمى)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+7 قنوات", "specialty": "مسؤولة تسويق ونمو قنوات التداول"},
    {"rank": 20, "username": "@MOKHTARR1", "name": "Mokhtar Ads (مختار)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+7 قنوات", "specialty": "ميديا باير وإدارة إعلانات الفوركس والشراكات"},
    {"rank": 21, "username": "@AdSwift", "name": "AdSwift Agency", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+7 قنوات", "specialty": "وكالة ترويج مالي وشراء ترافيك وحملات"},
    {"rank": 22, "username": "@Lamar_Ads", "name": "Lamar Ads (لمار)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+6 قنوات", "specialty": "إدارة إعلانات وتبادل نشر يومي مباشر"},
    {"rank": 23, "username": "@HayamAd2j", "name": "Hayam Ads (هيام)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+6 قنوات", "specialty": "مسؤولة تبادل إعلاني وترويج قنوات"},
    {"rank": 24, "username": "@Jamilaads", "name": "Jamila Ads (جميلة)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+6 قنوات", "specialty": "ترويج منصات وقنوات VIP"},
    {"rank": 25, "username": "@nancy_ads1", "name": "Nancy Ads (نانسي)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+6 قنوات", "specialty": "مسؤولة إعلانات قنوات نشطة"},
    {"rank": 26, "username": "@rahma4565", "name": "Rahma Ads (رحمة)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+6 قنوات", "specialty": "تبادل إعلاني وتزويد تفاعل"},
    {"rank": 27, "username": "@lis_anihad", "name": "Nihad Trading (نهاد)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+5 قنوات", "specialty": "مسؤولة تواصل وإعلانات في قنوات المليونير"},
    {"rank": 28, "username": "@nahed_ads", "name": "Nahed Ads (ناهد)", "tier": "Tier 2 (متوسطة - نشطة)", "channels_count": "+5 قنوات", "specialty": "حساب حجز وتبادل إعلانات القنوات"},

    # Tier 3
    {"rank": 29, "username": "@joee_ads", "name": "Joee Ads (جو)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+4 قنوات", "specialty": "تسويق قنوات وتبادل إعلاني"},
    {"rank": 30, "username": "@AdsSafwat", "name": "Safwat Ads (صفوت)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+4 قنوات", "specialty": "إدارة إعلانات تجارية وتمويل"},
    {"rank": 31, "username": "@Emanads000", "name": "Eman Ads 2", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+4 قنوات", "specialty": "حساب استقبال إعلانات فرعي"},
    {"rank": 32, "username": "@faridaads", "name": "Farida Ads 2", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+4 قنوات", "specialty": "حساب فرعي لفريدة إعلانات"},
    {"rank": 33, "username": "@Mairaads", "name": "Maira Ads (مايرا)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+4 قنوات", "specialty": "ترويج ونشر وتبادل قنوات"},
    {"rank": 34, "username": "@lina_bnm", "name": "Lina (لينا)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "تبادل إعلاني وتوجيه منشورات"},
    {"rank": 35, "username": "@mai_promoter", "name": "Mai Promoter (مي)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "بروموشن وزيادة مشاهدات وتفاعل"},
    {"rank": 36, "username": "@abdo0o0o0oo", "name": "Abdo Ads (عبده)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "إدارة إعلانات قنوات"},
    {"rank": 37, "username": "@MohammedAds33", "name": "Mohammed Ads 33", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "ترويج قنوات تداول"},
    {"rank": 38, "username": "@AesyGul", "name": "Aesy Gul", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "تبادل نشر وتفاعل"},
    {"rank": 39, "username": "@Maha2210", "name": "Maha Ads (مها)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "مسؤولة تبادل إعلاني"},
    {"rank": 40, "username": "@Elsaidd22", "name": "Elsaid Ads (السيد)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "إعلانات وتمويل قنوات"},
    {"rank": 41, "username": "@uniqads2", "name": "Uniq Ads", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "خدمات ترويج قنوات"},
    {"rank": 42, "username": "@Meromero3131", "name": "Mero Mero (ميرو)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "تبادل ونشر قنوات"},
    {"rank": 43, "username": "@mayar_medhat1012", "name": "Mayar Medhat (ميار)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "مسؤولة إعلانات قنوات"},
    {"rank": 44, "username": "@Abou_yaqoub", "name": "Abou Yaqoub (أبو يعقوب)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "إدارة قنوات وتواصل إعلاني"},
    {"rank": 45, "username": "@EmaAds", "name": "Ema Ads (إيما)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+3 قنوات", "specialty": "ترويج وتبادل قنوات"},
    {"rank": 46, "username": "@Stateuntied_ads", "name": "Stateunited Ads", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+2 قنوات", "specialty": "إعلانات قنوات متنوعة"},
    {"rank": 47, "username": "@Khaled_ads", "name": "Khaled Ads (خالد)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+2 قنوات", "specialty": "شراء مساحات إعلانية"},
    {"rank": 48, "username": "@malak_ads22", "name": "Malak Ads 22 (ملك)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+2 قنوات", "specialty": "تبادل إعلاني وتزويد متابعين"},
    {"rank": 49, "username": "@Maya_ADS1", "name": "Maya Ads (مايا)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+2 قنوات", "specialty": "إعلانات وترويج قنوات"},
    {"rank": 50, "username": "@Node231", "name": "Node Ads (نود)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+2 قنوات", "specialty": "تبادل نشر وتوجيه"},
    {"rank": 51, "username": "@Dododede23", "name": "Dodo Dede (دودو)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+2 قنوات", "specialty": "إعلانات قنوات تفاعلية"},
    {"rank": 52, "username": "@Malaaaakads", "name": "Malak Ads (ملاك)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+2 قنوات", "specialty": "مسؤولة تبادل قنوات"},
    {"rank": 53, "username": "@Mohamedben392", "name": "Mohamed Ben", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+2 قنوات", "specialty": "إدارة وتنسيق قنوات"},
    {"rank": 54, "username": "@Ggfigt", "name": "Ggfigt Ads", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+2 قنوات", "specialty": "تبادل قنوات"},
    {"rank": 55, "username": "@zeyad3112", "name": "Zeyad Ads (زياد)", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+2 قنوات", "specialty": "ميديا باير وترويج"},
    {"rank": 56, "username": "@ADSONLYF", "name": "Ads Only Official", "tier": "Tier 3 (مباشرة ومسوقون)", "channels_count": "+2 قنوات", "specialty": "حساب مخصص للإعلانات فقط"}
]

# Write CSV file
csv_file_path = "advertisers_master_list.csv"
with open(csv_file_path, mode='w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerow(["#", "Username", "Display Name", "Tier", "Channels Count", "Specialty / Focus"])
    for row in ranked_advertisers:
        writer.writerow([row["rank"], row["username"], row["name"], row["tier"], row["channels_count"], row["specialty"]])

# Write plain text usernames list
txt_file_path = "advertisers_usernames_plain.txt"
with open(txt_file_path, mode='w', encoding='utf-8') as f:
    for row in ranked_advertisers:
        f.write(f"{row['username']}\n")

print(f"Generated {csv_file_path} and {txt_file_path} successfully for {len(ranked_advertisers)} advertisers.")
