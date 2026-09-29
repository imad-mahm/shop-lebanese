import re

CATEGORIES = {
    "Fashion": r"\b(dress(es)?|abayas?|shirts?|t-shirts?|jeans|pants|skirts?|hoodies?|jackets?|clothing|apparel|fashion|"
               r"modest wear|lingerie|swimwear|shoes|sneakers|heels|handbags?|bags)\b|فستان|ملابس|أزياء|عباية|أحذية|حقائب",
    "Jewellery & Accessories": r"\b(jewel(le)?ry|necklaces?|bracelets?|earrings?|diamonds?|gold|silver|pendants?|"
                               r"anklets?|sunglasses)\b|مجوهرات|اكسسوارات|إكسسوارات",
    "Beauty & Skincare": r"\b(skin ?care|make-?up|cosmetics?|serums?|lipsticks?|mascara|hair ?care|nail polish|beauty)\b"
                         r"|تجميل|مكياج|العناية بالبشرة",
    "Perfume": r"\b(perfumes?|fragrances?|parfums?|eau de|oud|musk|bakhoor)\b|عطور|عطر|بخور",
    "Home & Decor": r"\b(home decor|decor|furniture|candles?|cushions?|kitchenware|tableware|bedding|rugs?|vases?|"
                    r"linens?)\b|ديكور|أثاث|مفروشات",
    "Food & Sweets": r"\b(chocolates?|sweets|cakes?|cookies|pastr(y|ies)|coffee beans|ground coffee|arabic coffee|"
                     r"herbal teas?|tea bags|honey|olive oil|za'?atar|mouneh|spices|nuts|baklava|maamoul|groceries|"
                     r"grocery|snacks)\b|حلويات|شوكولا|مونة|زعتر|عسل|معمول",
    "Wine & Spirits": r"\b(wines?|whisk(e)?y|vodka|gin|rum|tequila|champagne|arak|spirits|liqueurs?|beers?|cabernet|"
                      r"merlot|chardonnay|vineyards?|ch[aâ]teau)\b|نبيذ|عرق",
    "Home Appliances": r"\b(appliances?|refrigerators?|fridges?|washing machines?|dishwashers?|ovens?|microwaves?|"
                       r"air ?fryers?|blenders?|kettles?|coffee machines?|espresso machines?|vacuum cleaners?|"
                       r"air conditioners?|heaters?|mixers?|water dispensers?)\b|غسالة|براد",
    "Gifts & Flowers": r"\b(gifts?|flowers?|bouquets?|hampers?|personali[sz]ed|customi[sz]ed|balloons|giveaways?)\b"
                       r"|هدايا|هدية|ورود|زهور",
    "Kids & Baby": r"\b(baby|babies|kids|children|toys?|newborn|diapers?|strollers?|maternity)\b|أطفال|ألعاب|مواليد",
    "Electronics": r"\b(electronics|laptops?|smartphones?|iphone|samsung|headphones|chargers?|gaming|consoles?|"
                   r"smart ?watch(es)?|computers?|tablets?)\b|الكترونيات|إلكترونيات|هواتف",
    "Sports & Outdoor": r"\b(sportswear|fitness|gym|yoga|camping|hiking|bicycles?|outdoor|activewear)\b|رياضة|رياضية",
    "Health & Supplements": r"\b(supplements?|vitamins?|protein|parapharmacy|pharmacy|wellness|organic)\b"
                            r"|مكملات|صيدلية|فيتامين",
    "Books & Stationery": r"\b(books?|stationery|notebooks?|planners?|journals?)\b|كتب|قرطاسية",
    "Pets": r"\b(pets?|dog food|cat food|puppy|kitten|aquarium)\b|حيوانات أليفة",
    "Art & Handmade": r"\b(handmade|hand-made|artisan(al)?|ceramics?|pottery|paintings?|art prints|embroider(y|ed)|"
                      r"crochet|macrame)\b|يدوي|صناعة يدوية",
}
_COMPILED = {name: re.compile(rx, re.I) for name, rx in CATEGORIES.items()}


def categorize(text, top=3):
    counts = {}
    for name, rx in _COMPILED.items():
        n = len(rx.findall(text))
        if n:
            counts[name] = n
    ranked = sorted(counts, key=counts.get, reverse=True)
    strong = [c for c in ranked if counts[c] >= 2][:top]
    return strong or ranked[:1]
