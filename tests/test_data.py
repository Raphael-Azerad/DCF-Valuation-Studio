from dcf_studio.data import is_financial_institution


def test_identifies_financial_institutions():
    assert is_financial_institution("Financial Services", "Banks - Diversified")
    assert is_financial_institution("Financials", "Insurance")
    assert not is_financial_institution("Technology", "Consumer Electronics")
