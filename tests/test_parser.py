from datetime import datetime

from scanner.edgar import parse_form4

SAMPLE = b"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000001</issuerCik>
    <issuerName>Acme Corp</issuerName>
    <issuerTradingSymbol>acme</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerName>Jane Doe</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isOfficer>1</isOfficer>
      <isDirector>0</isDirector>
      <officerTitle>CFO</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-01-15</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>12.50</value></transactionPricePerShare>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>5000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-01-15</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><value>13.00</value></transactionPricePerShare>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>4500</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


def test_parser_keeps_only_purchases():
    trades = list(parse_form4(SAMPLE, "0000-acc", datetime(2026, 1, 16)))
    assert len(trades) == 1
    t = trades[0]
    assert t.issuer_ticker == "ACME"
    assert t.transaction_code == "P"
    assert t.shares == 1000
    assert t.price == 12.5
    assert t.dollar_value == 12_500
    assert t.is_officer is True
    assert t.insider_title == "CFO"
