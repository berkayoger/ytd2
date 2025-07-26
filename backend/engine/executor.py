from .data_loader import load_sample_price_data
from .feature_engineering import compute_features
from .model_runner import run_simple_rule_model
from .decision_maker import build_prediction


def generate_prediction_for(symbol="BTC"):
    df = load_sample_price_data(symbol)
    df_feat = compute_features(df)
    model_out = run_simple_rule_model(df_feat)
    result = build_prediction(df_feat, model_out)
    return result
