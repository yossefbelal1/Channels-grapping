import asyncio
import os
import sys
from telethon import TelegramClient

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tg_manager import get_session_path

OLD_72_LIST = [
    ("Arab ICT مجمتع", "ArabICTCommunity", -1004439813625),
    ("AlMANSORI 📊", "Almansori_11", -1002047969365),
    ("ETh Crypto Vip AI", None, -1003995558221),
    ("KING FX💯🔥", "KING2024FX", -1001789800455),
    ("FOREX ⇅ PALESTINE 🇵🇸", None, -1001983755992),
    ("⚡️⚡️جلااااد الذهب والمؤشرات⚡️⚡️", None, -1004424333854),
    ("🔥 Dr ALi FOREX 🔥", "dr_ali_forex", -1002335367368),
    ("🔥 Dr ALi CRYPTO 🔥", "dr_ali_crypto", -1002030415871),
    ("Silver VIP AI", None, -1003244891246),
    ("Gold Vip Ai", None, -1004411682552),
    ("Usd/Euro Vip AI", None, -1004360293327),
    ("Oil Vip AI", None, -1004407134120),
    ("BTC Crypto ViP AI", None, -1003971729838),
    ("Future Coin Crypto Vip AI", None, -1004406972503),
    ("Spot Alpha Crypto VIP AI", None, -1004412914305),
    ("Future Meme Crypto Vip AI", None, -1004346509472),
    ("Spot Coin Crypto Vip AI", None, -1004488372553),
    ("سيادة💎 الذهب🥇GOLD", "sssesssessse", -1003954807820),
    ("قناة دللني على الذهب 📊🪙", "tradingeagles121", -1002455664121),
    ("SNIPER GOLD", "Lady_ALGold", -1001531870553),
    ("رناي 👑 ملكة التداول | RNAI Trading Queen 👑", None, -1002424695877),
    ("𝑷𝒓𝒐𝒇𝒆𝒔𝒔𝒐𝒓 𝑨𝒍-𝑫𝒂𝒉𝒂𝒑📊🔥", None, -1002703759874),
    ("🇬🇧𝐔𝐊 𝐓𝐑𝐀𝐃𝐄𝐑'𝐒🇬🇧", "Join_trading_zone10", -1003331294074),
    ("🇸🇦 الفوركس في المملكة العربية السعودية 🇸🇦", "join_Gold_sniper_signals", -1003594337653),
    ("🔥𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗠𝗔𝗡𝗔𝗚𝗘𝗥🔥", "join_account_manager", -1003774865254),
    ("👑 𝙏𝙚𝙘𝙝𝙣𝙞𝙘𝙖𝙡_𝙖𝙣𝙖𝙡𝙮𝙨𝙞s 👑", "technicalanalysis25", -1004323566851),
    ("توصيات ذهب فوركس Forex AZ Gold", "xauusdu7", -1002647711700),
    ("الأسطورة للتداول", "Legend_2_Trading", -1003556765779),
    ("منصه تداول العملات الرقمية", "EliteGoldTheLegend", -1003981896156),
    ("العملات الرقمية VIP", "Gold_SecretsVIP", -1003934332055),
    ("الاسطورة للتدوال", "Legend_0_Trading", -1003228230471),
    ("الاسطورة الذهب", "Gold_CapitalVIP", -1003956168267),
    ("منصات تدوال العملات الرقمية", "LXAUVIP", -1003949998428),
    ("منصات تدوال العملات الرقمية", "LGoldVIP", -1003874858448),
    ("متداولو المليون 💵", "hhhjjkkkk8iy", -1003936577637),
    ("الاسطورة للتداول", "GoldBossVIP", -1003818741323),
    ("قروب تداول العملات الرقمية", "XAU_CrownVIP", -1003954606810),
    ("الحيتان مع الأسطورة 🐋", "Pump_966_1", -1003943420895),
    ("إشارات العملات المضمونة 🎯", "Gold_EagleVIP", -1003977228295),
    ("ملوك العملات الرقمية 💎", "Forex_SecretsVIP", -1003894767181),
    ("قروب مناقشة البتكوين ₿ Bitcoin", "LVIPFX", -1003788389342),
    ("مجتمع تدول العملات الرقمية", "OstoraFX", -1003753008263),
    ("البامبات العربيه🇸🇦الاستثمار الناجحه🇸🇦🇸🇦", "LegendLive1", -1003955838511),
    ("أساطير الفوركس 🔥", "MarketHuntersVIP", -1003997623648),
    ("عرش الاسطورة", "OstoraSignals", -1003786045428),
    ("صناع الثروة 💵", "Legend_1_Trading1", -1003984623741),
    ("محمد المطيري تداول", "MohammedAlMutairi11", -1003745828370),
    ("PRIME PIPS 🐋", "TRAED_ELAZAIZY0", -1003382147473),
    ("💥💥الجوكر ملك الذهب والفضه💥💥", "MyChannel2032", -1003842394957),
    ("forex signal", None, -1003971919365),
    ("PiP TRADER", "PiPTRADER_fx", -1004422809469),
    ("Sherlock Holmes FX", "sherlockholmesfx", -1002132146000),
    ("Prime Trading", "primetrading100", -1003493935476),
    ("‏MORX", None, -1002125984562),
    ("BLACK HORSE ACADEMY 🔥", "black_Horse944", -1003964939153),
    ("Smart Liquidity", "LOCAL_FX1", -1003162275358),
    ("⚜𝙏𝙍𝘼𝘿𝙄𝙉𝙂 𝙀𝙈𝙋𝙄𝙍🇪⚜", None, -1003834026329),
    ("ماستر تداول الفوركس", None, -1001526351755),
    ("MAFIA GOLD", None, -1004298874694),
    ("THE ROYAL VAULT🔥🃏♠️", None, -1003876055400),
    ("AT. TRADING 📉", None, -1003799397404),
    ("💎 𝙀𝘼𝙂𝙇🇪 𝙋𝙄𝙋𝙎 𝙋𝙍𝙊", "goldplatinum_trader02", -1003935334777),
    ("3abkreno ElForex | توصيات الذهب", "abkrenoelforex", -1001619031352),
    ("Trade X 🔱", None, -1002374105768),
    ("Pip Masters", None, -1003999757764),
    ("🔥 𝙂𝙊𝙇𝘿 𝙋𝙍𝙊 𝙏𝙍𝘼𝘿🇪𝙍 🔥", None, -1003554147110),
    ("GOLD GENERAL", "GOLDGENRal001", -1003514965887),
    ("خدمة إدارة الحسابات", None, -1003919625643),
    ("ARAB ICT 🔐", "arabictchannel", -1001222348201),
    ("ادارة حسابات تداول الفوركس", "adarhh", -1003115432387)
]

async def main():
    session_path = get_session_path("user_session")
    client = TelegramClient(session_path, 36318125, '5f2ea025376141a257979750c3fc9cf7')
    await client.connect()
    if not await client.is_user_authorized():
        print("user_session NOT authorized!")
        await client.disconnect()
        return

    print("Fetching all dialogs (active + archived)...")
    d_active = await client.get_dialogs(limit=None)
    d_archived = []
    try:
        d_archived = await client.get_dialogs(limit=None, folder=1)
    except Exception:
        pass

    all_dialogs = d_active + d_archived
    dialog_map = {d.id: d for d in all_dialogs}

    print(f"\n--- COMPARING 72 CHANNELS WITH CURRENT STATUS ---")
    missing_admin_count = 0
    
    for name, uname, cid in OLD_72_LIST:
        d = dialog_map.get(cid)
        if not d:
            print(f"❌ NOT IN DIALOGS (Left/Kicked/Deleted): '{name}' (@{uname}) [id={cid}]")
            missing_admin_count += 1
        else:
            ent = d.entity
            creator = getattr(ent, 'creator', False)
            admin_rights = getattr(ent, 'admin_rights', None)
            is_admin = getattr(ent, 'admin', False)
            left = getattr(ent, 'left', False)
            kicked = getattr(ent, 'kicked', False)

            if left or kicked:
                print(f"⚠️ LEFT OR KICKED: '{name}' (@{uname}) [id={cid}]")
                missing_admin_count += 1
            elif not creator and admin_rights is None and not is_admin:
                print(f"🔻 DEMOTED FROM ADMIN: '{name}' (@{uname}) [id={cid}]")
                missing_admin_count += 1

    print(f"\nTotal Channels Demoted or Removed from Admin: {missing_admin_count}")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
