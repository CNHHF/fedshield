# -*- coding: utf-8 -*-
"""FedShield 核心算法自测（标准库 unittest，可直接 python -m unittest 运行）。

覆盖范围：
- 密码学基础：SM4 国标向量、Paillier 同态运算、AES-GCM 往返、PSI 求交、差分隐私
- 隐私计算引擎：匿踪查询（双模式）、联合统计、联邦学习（含差分隐私与密文聚合）
- 合规引擎：智能分级、规则引擎（阻断/整改/放行）、法规库留存年限
- 审计存证：链式哈希与篡改检测

运行：
    cd fedshield
    python -m unittest discover -s backend/tests -v
"""

from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.compliance import classifier, regulation_lib, rule_engine  # noqa: E402
from backend.crypto import dp, paillier, policy, psi, sm4  # noqa: E402
from backend.engine import federated, joint_stats, oblivious  # noqa: E402


class TestCrypto(unittest.TestCase):
    """密码学与隐私计算基础库。"""

    def test_sm4_standard_vectors(self):
        """GB/T 32907-2016 标准测试向量。"""
        key = bytes.fromhex("0123456789abcdeffedcba9876543210")
        plain_block = bytes.fromhex("0123456789abcdeffedcba9876543210")

        cipher_block = sm4.encrypt_block_vector(key, plain_block)
        self.assertEqual(cipher_block.hex(), "681edf34d206965e86b3e94f536e4246")
        self.assertEqual(sm4.decrypt_block_vector(key, cipher_block), plain_block)

        # 标准向量二：同一分组加密 1,000,000 次
        block = plain_block
        for _ in range(1_000_000):
            block = sm4.encrypt_block_vector(key, block)
        self.assertEqual(block.hex(), "595298c7c6fd271f0402f804c33d3f66")

    def test_sm4_cbc_roundtrip_and_tamper(self):
        key, _salt = sm4.derive_key("fedshield-demo")
        token = sm4.encrypt(key, "跨境支付 P1 级敏感数据")
        self.assertEqual(sm4.decrypt_text(key, token), "跨境支付 P1 级敏感数据")

        tampered = token[:-4] + ("0000" if token[-4:] != "0000" else "1111")
        with self.assertRaises(ValueError):
            sm4.decrypt(key, tampered)

    def test_paillier_homomorphic(self):
        public_key, private_key = paillier.generate_keypair(512)
        cipher = paillier.PaillierCipher(public_key, private_key)

        first, second = cipher.encrypt(12345), cipher.encrypt(6789)
        self.assertEqual(cipher.decrypt(cipher.add(first, second)), 12345 + 6789)
        self.assertEqual(cipher.decrypt(cipher.scalar_mul(first, 7)), 12345 * 7)
        self.assertEqual(cipher.decrypt(cipher.add_plain(first, -12345)), 0)
        # CRT 解密与直接解密结果一致
        direct = paillier.PaillierCipher(
            public_key, paillier.PaillierPrivateKey(lam=private_key.lam, mu=private_key.mu, public_key=public_key)
        )
        self.assertEqual(direct.decrypt(first), cipher.decrypt(first))

    def test_psi_intersection(self):
        left = ["ACME GmbH", "Tehran Petro Co", "深圳跨境优选", "Shanghai B2B"]
        right = ["ACME GmbH", "Tehran Petro Co", "Pyongyang Shipping"]
        result = psi.run_psi(left, right)
        self.assertEqual(sorted(result["intersection"]), ["ACME GmbH", "Tehran Petro Co"])
        # 仅返回交集，不泄露其余元素
        self.assertNotIn("上海", "".join(result["intersection"]))

    def test_differential_privacy(self):
        account = dp.BudgetAccount(total=10.0)
        first = account.spend(2.0, scene="联合建模", project="反欺诈模型训练")
        self.assertAlmostEqual(first["remaining"], 8.0, places=6)
        with self.assertRaises(ValueError):
            account.spend(20.0)

        allocation = dp.allocate_budget(
            8.0,
            [
                {"name": "收付款方信息", "level": "P1", "contribution": 0.9},
                {"name": "商品类别", "level": "P3", "contribution": 0.3},
            ],
        )
        # 高敏感数据应获得更高的隐私预算保护强度
        self.assertGreater(allocation[0]["epsilon"], allocation[1]["epsilon"])

        # ε=2 时精度损失约 7%（对应文档指标）
        impact = dp.noise_impact(2.0)
        self.assertLess(abs(impact["accuracyLoss"] - 0.07), 0.01)

    def test_graded_encryption_policy(self):
        envelope = policy.encrypt_payload("P1", {"name": "张三", "cardNo": "6222021234567890"})
        self.assertEqual(envelope["level"], "P1")
        self.assertIn("SM4", envelope["cipher"])
        self.assertEqual(policy.decrypt_payload(envelope)["cardNo"], "6222021234567890")

        noisy = policy.encrypt_payload("P2", {"amount": 10000.0}, epsilon=1.5)
        self.assertNotEqual(policy.decrypt_payload(noisy)["amount"], 10000.0)

        vector = policy.protect_vector("P1", [1.5, 2.25, 3.125])
        self.assertEqual(policy.open_vector(vector), [1.5, 2.25, 3.125])


class TestEngine(unittest.TestCase):
    """隐私计算引擎三大场景。"""

    def setUp(self):
        self.lists = {
            "OFAC": [
                {"name": "Tehran Petro Trading Co", "taxNo": "IR-88213", "country": "Iran", "program": "SDN"},
                {"name": "ACME GmbH", "taxNo": "DE-99120", "country": "Germany", "program": "SDN"},
            ],
            "UN": [
                {"name": "Pyongyang Shipping Lines", "taxNo": "KP-10021", "country": "DPRK", "program": "UNSC"}
            ],
        }

    def test_oblivious_query_both_modes(self):
        for mode in ("oprf", "paillier"):
            hit = oblivious.oblivious_query(["Tehran Petro Trading Co", "IR-88213"], self.lists, mode=mode)
            self.assertTrue(hit["hit"], f"{mode} 模式未命中")
            self.assertIn("OFAC", hit["matchedList"])
            self.assertEqual(hit["privacy"]["queryPlaintextExposed"], 0)
            self.assertEqual(hit["privacy"]["listPlaintextExposed"], 0)

            miss = oblivious.oblivious_query(["Not Listed Trading Ltd", "XX-0000"], self.lists, mode=mode)
            self.assertFalse(miss["hit"], f"{mode} 模式误命中")

    def test_joint_statistics_accuracy(self):
        rng = random.Random(2026)
        transactions = [
            {
                "region": region,
                "amount": round(rng.lognormvariate(9.0, 0.6), 2),
                "category": rng.choice(["电子产品", "服饰鞋帽"]),
                "counterparties": rng.randint(1, 4),
                "level": "P2",
            }
            for region in ("CN", "EU", "SEA")
            for _ in range(200)
        ]
        result = joint_stats.joint_statistics(transactions, epsilon=1.5)
        self.assertLessEqual(result["errorRate"], 0.01)  # 误差率指标 ≤1%
        self.assertTrue(result["errorPass"])
        self.assertEqual(len(result["byRegion"]), 3)
        self.assertGreater(result["counterpartyTotal"], 0)  # 密文域求和有效

    def test_federated_learning_quality(self):
        """联邦联合建模应显著优于单地区本地建模，且与明文建模差距 ≤0.02。"""
        meta = {
            "EU-FRA": {"name": "欧盟法兰克福节点", "region": "EU"},
            "CN-HGH": {"name": "中国杭州节点", "region": "CN"},
            "SG-SIN": {"name": "新加坡节点", "region": "SEA"},
        }
        nodes = federated.build_nodes(["EU-FRA", "CN-HGH", "SG-SIN"], meta)
        result = federated.federated_train(nodes, rounds=8, epsilon=2.0)

        metrics = result["metrics"]
        self.assertGreaterEqual(metrics["auc"], 0.80)
        self.assertLessEqual(metrics["missRate"], 0.07)  # 漏检率红线 ≤7%
        self.assertTrue(metrics["missRatePass"])
        self.assertGreater(result["baseline"]["aucGainOverLocal"], 0.05)
        self.assertTrue(result["baseline"]["aucGapPass"])  # 与明文 AUC 偏差 ≤0.02
        self.assertGreater(result["homomorphic"]["ciphertexts"], 0)
        self.assertGreater(result["traffic"]["savedPercent"], 40)


class TestCompliance(unittest.TestCase):
    """合规引擎。"""

    def test_classifier(self):
        result = classifier.classify_fields(
            [
                {"name": "身份证号", "sample": "310101199001011234"},
                {"name": "银行卡号", "sample": "6222021234567890123"},
                {"name": "交易金额", "sample": "1280.50"},
                {"name": "商品类别", "sample": "电子产品"},
            ]
        )
        levels = [item["level"] for item in result["results"]]
        self.assertEqual(levels[:2], ["P1", "P1"])
        self.assertEqual(levels[2], "P2")
        self.assertEqual(levels[3], "P3")
        self.assertGreaterEqual(result["averageConfidence"], 0.9)

    def test_rule_engine_blocks_illegal_transfer(self):
        rules = rule_engine.default_rules()
        context = {
            "event": "data.transfer", "dataLevel": "P1", "sourceRegion": "CN", "targetRegion": "EU",
            "crossBorder": True, "hasScc": False, "hasDpia": False, "authorized": False,
            "purpose": "营销推广", "fieldCount": 8000,
        }
        result = rule_engine.evaluate(rules, context)
        self.assertFalse(result["passed"])
        self.assertTrue(result["blocked"])
        self.assertTrue(result["rectificationList"])

    def test_rule_engine_allows_compliant_transfer(self):
        rules = rule_engine.default_rules()
        context = {
            "event": "data.transfer", "dataLevel": "P2", "sourceRegion": "CN", "targetRegion": "SG",
            "crossBorder": True, "hasScc": True, "hasDpia": True, "authorized": True,
            "purpose": "反欺诈模型训练", "fieldCount": 120,
        }
        result = rule_engine.evaluate(rules, context)
        self.assertTrue(result["passed"])
        self.assertFalse(result["blocked"])

    def test_regulation_retention(self):
        self.assertEqual(regulation_lib.get("GDPR")["auditRetentionYears"], 7)
        self.assertEqual(regulation_lib.get("PIPL")["auditRetentionYears"], 5)
        coverage = regulation_lib.coverage_stats()
        self.assertGreaterEqual(coverage["total"], 180)
        self.assertGreater(coverage["verifiedCount"], 20)


class TestAudit(unittest.TestCase):
    """审计存证链式哈希。"""

    def test_chain_hash_and_tamper(self):
        from backend.audit import chain

        digest = chain.payload_digest({"action": "oblivious.query", "actor": "risk.officer"})
        first = chain.compute_hash(chain.GENESIS_HASH, digest, "tx-001", "2026-05-18 10:00:00.000000")
        second = chain.compute_hash(first, digest, "tx-002", "2026-05-18 10:00:01.000000")
        self.assertEqual(len(first), 64)
        self.assertNotEqual(first, second)

        # 篡改载荷 → 摘要变化 → 链校验必然失败
        tampered = chain.payload_digest({"action": "oblivious.query", "actor": "attacker"})
        self.assertNotEqual(digest, tampered)
        self.assertNotEqual(
            chain.compute_hash(chain.GENESIS_HASH, tampered, "tx-001", "2026-05-18 10:00:00.000000"), first
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
