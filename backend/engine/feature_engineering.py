def compute_features(df):
    df["sma_10"] = df["price"].rolling(window=10).mean()
    df["momentum"] = df["price"].diff()
    return df.dropna()
