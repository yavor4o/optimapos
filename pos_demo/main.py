"""
🏢 SAP BUSINESS POS SYSTEM - PYSIDE6
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Enterprise-grade POS system with SAP Fiori 3 design principles
Professional business application with modern UI/UX

Installation:
pip install PySide6

Usage:
python sap_pos.py
"""

import sys
import json
from decimal import Decimal
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QFrame, QMessageBox, QScrollArea,
    QDialog, QSizePolicy, QStackedWidget, QButtonGroup,
    QSpacerItem, QGraphicsDropShadowEffect
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QSize, QPropertyAnimation,
    QEasingCurve, QRect, QPoint, Property, QDateTime
)
from PySide6.QtGui import (
    QFont, QPalette, QColor, QPixmap, QIcon, QPainter,
    QLinearGradient, QBrush, QPen, QFontDatabase
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🎨 SAP FIORI 3 COLOR SYSTEM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SAPColors:
    """SAP Fiori 3 Design System Colors"""

    # Primary Brand Colors
    BRAND_PRIMARY = "#0a6ed1"
    BRAND_HOVER = "#085caf"
    BRAND_ACTIVE = "#074c8f"

    # Shell Colors
    SHELL_HEADER = "#354a5f"
    SHELL_HOVER = "#283848"

    # Semantic Colors
    SUCCESS = "#107e3e"
    SUCCESS_BG = "#e8f5e9"
    WARNING = "#df6e0c"
    WARNING_BG = "#fff3e0"
    ERROR = "#bb0000"
    ERROR_BG = "#ffebee"
    INFORMATION = "#0a6ed1"
    INFORMATION_BG = "#e8f4fd"

    # Grey Scale
    WHITE = "#ffffff"
    GREY_1 = "#fafafa"
    GREY_2 = "#f5f5f5"
    GREY_3 = "#ededed"
    GREY_4 = "#e5e5e5"
    GREY_5 = "#d9d9d9"
    GREY_6 = "#cccccc"
    GREY_7 = "#999999"
    GREY_8 = "#666666"
    GREY_9 = "#32363a"
    BLACK = "#000000"

    # Shadows
    SHADOW_1 = "0px 2px 4px rgba(0,0,0,0.08)"
    SHADOW_2 = "0px 8px 16px rgba(0,0,0,0.08)"
    SHADOW_3 = "0px 16px 32px rgba(0,0,0,0.08)"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📦 DATA MODELS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ProductType(Enum):
    REGULAR = "regular"
    WEIGHT = "weight"


@dataclass
class Product:
    id: int
    sku: str
    name: str
    price: Decimal
    category: str
    stock: int
    is_weight: bool
    unit: str = "pcs"

    def get_stock_status(self):
        if self.is_weight:
            return "weight"
        elif self.stock == 0:
            return "out"
        elif self.stock < 50:
            return "low"
        else:
            return "available"


@dataclass
class CartItem:
    product: Product
    quantity: Decimal
    unique_id: str
    timestamp: datetime

    @property
    def subtotal(self) -> Decimal:
        return self.product.price * self.quantity

    @property
    def tax(self) -> Decimal:
        return self.subtotal * Decimal("0.20")

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.tax


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🎨 SAP UI COMPONENTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SAPButton(QPushButton):
    """SAP Fiori styled button"""

    def __init__(self, text: str, button_type: str = "default", icon: str = None):
        super().__init__(text if not icon else f"{icon} {text}")
        self.button_type = button_type
        self.apply_style()

    def apply_style(self):
        styles = {
            "primary": (SAPColors.BRAND_PRIMARY, SAPColors.WHITE, SAPColors.BRAND_HOVER),
            "success": (SAPColors.SUCCESS, SAPColors.WHITE, "#0d6e33"),
            "warning": (SAPColors.WARNING, SAPColors.WHITE, "#c45500"),
            "error": (SAPColors.ERROR, SAPColors.WHITE, "#990000"),
            "default": (SAPColors.WHITE, SAPColors.GREY_9, SAPColors.GREY_2)
        }

        bg, fg, hover = styles.get(self.button_type, styles["default"])

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: {"1px solid " + SAPColors.GREY_5 if self.button_type == "default" else "none"};
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
                min-height: 40px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {bg};
            }}
        """)

        self.setCursor(Qt.PointingHandCursor)


class SAPShellBar(QFrame):
    """SAP Shell Bar (Header)"""

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        self.setFixedHeight(44)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {SAPColors.SHELL_HEADER};
                border: none;
            }}
        """)

        layout = QHBoxLayout()
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(24)

        # Logo and Title
        logo_section = QHBoxLayout()
        logo_section.setSpacing(12)

        logo = QLabel("📦")
        logo.setStyleSheet("font-size: 20px; background: transparent;")

        title = QLabel("POS Terminal")
        title.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.WHITE};
                font-size: 16px;
                font-weight: 600;
                background: transparent;
            }}
        """)

        logo_section.addWidget(logo)
        logo_section.addWidget(title)

        # Center - Time and Status
        self.time_label = QLabel()
        self.time_label.setStyleSheet(f"""
            QLabel {{
                color: rgba(255,255,255,0.9);
                font-size: 14px;
                background: transparent;
            }}
        """)

        self.status_badge = QLabel("● System Online")
        self.status_badge.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.SUCCESS};
                background-color: rgba(16,126,62,0.1);
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }}
        """)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(8)

        for icon in ["🔔", "❓", "👤"]:
            btn = QPushButton(icon)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {SAPColors.WHITE};
                    border: none;
                    border-radius: 4px;
                    padding: 8px;
                    font-size: 16px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255,255,255,0.1);
                }}
            """)
            btn.setCursor(Qt.PointingHandCursor)
            actions.addWidget(btn)

        # Layout assembly
        layout.addLayout(logo_section)
        layout.addStretch()
        layout.addWidget(self.time_label)
        layout.addWidget(self.status_badge)
        layout.addStretch()
        layout.addLayout(actions)

        self.setLayout(layout)

        # Update time
        self.update_time()
        timer = QTimer(self)
        timer.timeout.connect(self.update_time)
        timer.start(1000)

    def update_time(self):
        current = QDateTime.currentDateTime()
        self.time_label.setText(current.toString("dd.MM.yyyy • hh:mm:ss"))


class SAPSidebar(QFrame):
    """SAP Sidebar Navigation"""
    category_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.categories = [
            {"id": "all", "name": "All Products", "icon": "📋"},
            {"id": "beverages", "name": "Beverages", "icon": "🥤"},
            {"id": "produce", "name": "Produce", "icon": "🍎"},
            {"id": "bakery", "name": "Bakery", "icon": "🍞"},
            {"id": "dairy", "name": "Dairy", "icon": "🥛"},
            {"id": "meat", "name": "Meat", "icon": "🥩"},
        ]
        self.active_category = "all"
        self.setup_ui()

    def setup_ui(self):
        self.setFixedWidth(240)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {SAPColors.WHITE};
                border-right: 1px solid {SAPColors.GREY_4};
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("CATEGORIES")
        header.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.GREY_8};
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.5px;
                padding: 20px 16px 12px 16px;
                background: transparent;
            }}
        """)
        layout.addWidget(header)

        # Category buttons
        self.category_buttons = []
        for category in self.categories:
            btn = self.create_category_button(category)
            self.category_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Status section
        status_frame = QFrame()
        status_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {SAPColors.WARNING_BG};
                border: 1px solid {SAPColors.WARNING};
                border-radius: 8px;
                margin: 16px;
            }}
        """)

        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(12, 12, 12, 12)

        warning_label = QLabel("⚠️ 3 Low Stock Items")
        warning_label.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.WARNING};
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            }}
        """)
        warning_label.setAlignment(Qt.AlignCenter)

        status_layout.addWidget(warning_label)
        status_frame.setLayout(status_layout)

        layout.addWidget(status_frame)
        self.setLayout(layout)

    def create_category_button(self, category: dict) -> QPushButton:
        btn = QPushButton(f"{category['icon']}  {category['name']}")
        btn.setProperty("category_id", category['id'])

        is_active = category['id'] == self.active_category
        self.update_button_style(btn, is_active)

        btn.clicked.connect(lambda: self.select_category(category['id']))
        btn.setCursor(Qt.PointingHandCursor)

        return btn

    def update_button_style(self, btn: QPushButton, is_active: bool):
        if is_active:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {SAPColors.INFORMATION_BG};
                    color: {SAPColors.BRAND_PRIMARY};
                    border: none;
                    border-left: 3px solid {SAPColors.BRAND_PRIMARY};
                    padding: 14px 16px;
                    text-align: left;
                    font-size: 14px;
                    font-weight: 600;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {SAPColors.GREY_9};
                    border: none;
                    border-left: 3px solid transparent;
                    padding: 14px 16px;
                    text-align: left;
                    font-size: 14px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {SAPColors.GREY_2};
                }}
            """)

    def select_category(self, category_id: str):
        self.active_category = category_id
        for btn in self.category_buttons:
            is_active = btn.property("category_id") == category_id
            self.update_button_style(btn, is_active)
        self.category_selected.emit(category_id)


class SAPProductCard(QFrame):
    """SAP styled product card"""
    clicked = Signal(Product)

    def __init__(self, product: Product):
        super().__init__()
        self.product = product
        self.setup_ui()

    def setup_ui(self):
        self.setFixedSize(220, 260)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {SAPColors.WHITE};
                border: 1px solid {SAPColors.GREY_4};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border-color: {SAPColors.BRAND_PRIMARY};
                background-color: {SAPColors.GREY_1};
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # SKU
        sku_label = QLabel(self.product.sku)
        sku_label.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.GREY_7};
                font-size: 11px;
                background: transparent;
            }}
        """)

        # Product name
        name_label = QLabel(self.product.name)
        name_label.setWordWrap(True)
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.GREY_9};
                font-size: 14px;
                font-weight: 500;
                background: transparent;
                min-height: 40px;
            }}
        """)

        # Price
        price_text = f"€{self.product.price:.2f}"
        if self.product.is_weight:
            price_text += "/kg"

        price_label = QLabel(price_text)
        price_label.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.BRAND_PRIMARY};
                font-size: 20px;
                font-weight: 600;
                background: transparent;
            }}
        """)

        # Stock status
        status = self.product.get_stock_status()
        status_configs = {
            "available": (f"✓ In Stock ({self.product.stock})", SAPColors.SUCCESS, SAPColors.SUCCESS_BG),
            "low": (f"⚠ Low Stock ({self.product.stock})", SAPColors.WARNING, SAPColors.WARNING_BG),
            "out": ("✗ Out of Stock", SAPColors.ERROR, SAPColors.ERROR_BG),
            "weight": ("⚖️ Weight Product", SAPColors.INFORMATION, SAPColors.INFORMATION_BG)
        }

        status_text, status_color, status_bg = status_configs[status]

        status_label = QLabel(status_text)
        status_label.setStyleSheet(f"""
            QLabel {{
                color: {status_color};
                background-color: {status_bg};
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
            }}
        """)
        status_label.setAlignment(Qt.AlignCenter)

        # Add shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setColor(QColor(0, 0, 0, 20))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

        layout.addWidget(sku_label)
        layout.addWidget(name_label)
        layout.addStretch()
        layout.addWidget(price_label)
        layout.addWidget(status_label)

        self.setLayout(layout)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.product)
        super().mousePressEvent(event)


class SAPCartPanel(QFrame):
    """SAP styled cart panel"""
    payment_requested = Signal()

    def __init__(self):
        super().__init__()
        self.cart_items: List[CartItem] = []
        self.setup_ui()

    def setup_ui(self):
        self.setFixedWidth(400)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {SAPColors.WHITE};
                border-left: 1px solid {SAPColors.GREY_4};
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setFixedHeight(80)
        header.setStyleSheet(f"""
            QFrame {{
                background: linear-gradient(135deg, {SAPColors.BRAND_PRIMARY} 0%, {SAPColors.BRAND_HOVER} 100%);
                border: none;
            }}
        """)

        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(20, 20, 20, 20)

        cart_title = QLabel("Shopping Cart")
        cart_title.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.WHITE};
                font-size: 18px;
                font-weight: 600;
                background: transparent;
            }}
        """)

        self.items_count = QLabel("0 items")
        self.items_count.setStyleSheet(f"""
            QLabel {{
                color: rgba(255,255,255,0.9);
                font-size: 14px;
                background: transparent;
            }}
        """)

        header_layout.addWidget(cart_title)
        header_layout.addWidget(self.items_count)
        header.setLayout(header_layout)

        # Cart items list
        self.cart_list = QListWidget()
        self.cart_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {SAPColors.GREY_1};
                border: none;
                padding: 8px;
                font-size: 13px;
            }}
            QListWidget::item {{
                background-color: {SAPColors.WHITE};
                border: 1px solid {SAPColors.GREY_4};
                border-radius: 8px;
                margin: 4px 0;
                padding: 12px;
                color: {SAPColors.GREY_9};
                min-height: 90px;
            }}
            QListWidget::item:hover {{
                border-color: {SAPColors.BRAND_PRIMARY};
                background-color: {SAPColors.INFORMATION_BG};
            }}
            QListWidget::item:selected {{
                background-color: {SAPColors.INFORMATION_BG};
                border-color: {SAPColors.BRAND_PRIMARY};
            }}
        """)

        # Summary
        self.summary_frame = QFrame()
        self.summary_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {SAPColors.GREY_1};
                border-top: 1px solid {SAPColors.GREY_4};
            }}
        """)

        summary_layout = QVBoxLayout()
        summary_layout.setContentsMargins(20, 20, 20, 20)
        summary_layout.setSpacing(12)

        self.subtotal_label = self.create_summary_row("Subtotal", "€0.00")
        self.tax_label = self.create_summary_row("VAT (20%)", "€0.00")

        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background-color: {SAPColors.GREY_5};")

        self.total_label = self.create_summary_row("Total", "€0.00", is_total=True)

        summary_layout.addLayout(self.subtotal_label)
        summary_layout.addLayout(self.tax_label)
        summary_layout.addWidget(separator)
        summary_layout.addLayout(self.total_label)

        self.summary_frame.setLayout(summary_layout)

        # Actions
        actions_frame = QFrame()
        actions_frame.setStyleSheet("background: transparent;")

        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(16, 16, 16, 16)
        actions_layout.setSpacing(12)

        clear_btn = SAPButton("Clear", "default", "🗑️")
        clear_btn.clicked.connect(self.clear_cart)

        payment_btn = SAPButton("Payment", "primary", "💳")
        payment_btn.clicked.connect(self.payment_requested.emit)

        actions_layout.addWidget(clear_btn)
        actions_layout.addWidget(payment_btn)

        actions_frame.setLayout(actions_layout)

        # Assembly
        layout.addWidget(header)
        layout.addWidget(self.cart_list, 1)
        layout.addWidget(self.summary_frame)
        layout.addWidget(actions_frame)

        self.setLayout(layout)
        self.update_display()

    def create_summary_row(self, label: str, value: str, is_total: bool = False) -> QHBoxLayout:
        layout = QHBoxLayout()

        label_widget = QLabel(label)
        value_widget = QLabel(value)

        if is_total:
            label_widget.setStyleSheet(f"""
                QLabel {{
                    color: {SAPColors.GREY_9};
                    font-size: 16px;
                    font-weight: 600;
                    background: transparent;
                }}
            """)
            value_widget.setStyleSheet(f"""
                QLabel {{
                    color: {SAPColors.BRAND_PRIMARY};
                    font-size: 20px;
                    font-weight: 600;
                    background: transparent;
                }}
            """)
        else:
            label_widget.setStyleSheet(f"""
                QLabel {{
                    color: {SAPColors.GREY_8};
                    font-size: 14px;
                    background: transparent;
                }}
            """)
            value_widget.setStyleSheet(f"""
                QLabel {{
                    color: {SAPColors.GREY_9};
                    font-size: 14px;
                    font-weight: 500;
                    background: transparent;
                }}
            """)

        layout.addWidget(label_widget)
        layout.addStretch()
        layout.addWidget(value_widget)

        # Store for updates
        layout.value_widget = value_widget

        return layout

    def add_item(self, product: Product, quantity: Decimal):
        # Check for existing item
        for item in self.cart_items:
            if item.product.id == product.id and not product.is_weight:
                item.quantity += quantity
                self.update_display()
                return

        # Add new item
        cart_item = CartItem(
            product=product,
            quantity=quantity,
            unique_id=f"{product.id}_{datetime.now().timestamp()}",
            timestamp=datetime.now()
        )

        self.cart_items.append(cart_item)
        self.update_display()

    def clear_cart(self):
        if self.cart_items:
            reply = QMessageBox.question(
                self, "Clear Cart",
                f"Remove {len(self.cart_items)} items from cart?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.cart_items.clear()
                self.update_display()

    def update_display(self):
        self.cart_list.clear()

        if not self.cart_items:
            # Empty cart message with better styling
            empty_widget = QWidget()
            empty_layout = QVBoxLayout()
            empty_layout.setAlignment(Qt.AlignCenter)

            icon_label = QLabel("🛒")
            icon_label.setAlignment(Qt.AlignCenter)
            icon_label.setStyleSheet("""
                font-size: 48px;
                color: #d9d9d9;
                background: transparent;
                padding: 20px;
            """)

            text_label = QLabel("Cart is empty\n\nAdd products to get started")
            text_label.setAlignment(Qt.AlignCenter)
            text_label.setStyleSheet(f"""
                color: {SAPColors.GREY_7};
                font-size: 14px;
                background: transparent;
                padding: 10px;
            """)

            empty_layout.addWidget(icon_label)
            empty_layout.addWidget(text_label)
            empty_widget.setLayout(empty_layout)

            item = QListWidgetItem()
            item.setSizeHint(empty_widget.sizeHint())
            self.cart_list.addItem(item)
            self.cart_list.setItemWidget(item, empty_widget)

            self.items_count.setText("0 items")
            self.subtotal_label.value_widget.setText("€0.00")
            self.tax_label.value_widget.setText("€0.00")
            self.total_label.value_widget.setText("€0.00")
            return

        # Update items with better formatting
        for cart_item in self.cart_items:
            # Create custom widget for cart item
            item_widget = QWidget()
            item_widget.setMinimumHeight(85)
            item_layout = QVBoxLayout()
            item_layout.setContentsMargins(8, 8, 8, 8)
            item_layout.setSpacing(6)

            # Product name
            name_label = QLabel(cart_item.product.name)
            name_label.setStyleSheet(f"""
                color: {SAPColors.GREY_9};
                font-size: 14px;
                font-weight: 600;
                background: transparent;
            """)

            # Quantity and price
            if cart_item.product.is_weight:
                qty_text = f"{cart_item.quantity:.3f} kg × €{cart_item.product.price:.2f}/kg"
            else:
                qty_text = f"{int(cart_item.quantity)} pcs × €{cart_item.product.price:.2f}"

            qty_label = QLabel(qty_text)
            qty_label.setStyleSheet(f"""
                color: {SAPColors.GREY_7};
                font-size: 12px;
                background: transparent;
            """)

            # Subtotal
            total_label = QLabel(f"Total: €{cart_item.subtotal:.2f}")
            total_label.setStyleSheet(f"""
                color: {SAPColors.BRAND_PRIMARY};
                font-size: 14px;
                font-weight: 600;
                background: transparent;
            """)

            item_layout.addWidget(name_label)
            item_layout.addWidget(qty_label)
            item_layout.addWidget(total_label)
            item_widget.setLayout(item_layout)

            # Add to list
            list_item = QListWidgetItem()
            list_item.setSizeHint(QSize(350, 95))
            self.cart_list.addItem(list_item)
            self.cart_list.setItemWidget(list_item, item_widget)

        # Update totals
        subtotal = sum(item.subtotal for item in self.cart_items)
        tax = sum(item.tax for item in self.cart_items)
        total = sum(item.total for item in self.cart_items)

        self.items_count.setText(f"{len(self.cart_items)} items")
        self.subtotal_label.value_widget.setText(f"€{subtotal:.2f}")
        self.tax_label.value_widget.setText(f"€{tax:.2f}")
        self.total_label.value_widget.setText(f"€{total:.2f}")


class SAPWeightDialog(QDialog):
    """SAP styled weight input dialog"""

    def __init__(self, parent, product: Product):
        super().__init__(parent)
        self.product = product
        self.weight_value = Decimal("0.500")
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Enter Product Weight")
        self.setFixedSize(500, 450)
        self.setModal(True)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {SAPColors.WHITE};
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Product info
        info_frame = QFrame()
        info_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {SAPColors.INFORMATION_BG};
                border: 1px solid {SAPColors.BRAND_PRIMARY};
                border-radius: 8px;
                padding: 16px;
            }}
        """)

        info_layout = QVBoxLayout()

        product_name = QLabel(self.product.name)
        product_name.setAlignment(Qt.AlignCenter)
        product_name.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.GREY_9};
                font-size: 18px;
                font-weight: 600;
                background: transparent;
            }}
        """)

        product_price = QLabel(f"€{self.product.price:.2f}/kg")
        product_price.setAlignment(Qt.AlignCenter)
        product_price.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.BRAND_PRIMARY};
                font-size: 24px;
                font-weight: 600;
                background: transparent;
                margin-top: 8px;
            }}
        """)

        info_layout.addWidget(product_name)
        info_layout.addWidget(product_price)
        info_frame.setLayout(info_layout)

        # Weight input
        weight_label = QLabel("Weight in kilograms:")
        weight_label.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.GREY_8};
                font-size: 14px;
                font-weight: 500;
            }}
        """)

        self.weight_input = QLineEdit("0.500")
        self.weight_input.setAlignment(Qt.AlignCenter)
        self.weight_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 16px;
                border: 2px solid {SAPColors.BRAND_PRIMARY};
                border-radius: 8px;
                font-size: 32px;
                font-weight: 600;
                color: {SAPColors.GREY_9};
                background-color: {SAPColors.WHITE};
            }}
            QLineEdit:focus {{
                border-color: {SAPColors.BRAND_HOVER};
                background-color: {SAPColors.GREY_1};
            }}
        """)
        self.weight_input.textChanged.connect(self.update_total)

        # Quick buttons
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(10)

        for weight in ["0.250", "0.500", "1.000", "2.000"]:
            btn = QPushButton(f"{weight} kg")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {SAPColors.WHITE};
                    color: {SAPColors.GREY_9};
                    border: 1px solid {SAPColors.GREY_5};
                    border-radius: 6px;
                    padding: 12px;
                    font-size: 14px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    border-color: {SAPColors.BRAND_PRIMARY};
                    background-color: {SAPColors.INFORMATION_BG};
                    color: {SAPColors.BRAND_PRIMARY};
                }}
            """)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, w=weight: self.weight_input.setText(w))
            quick_layout.addWidget(btn)

        # Total display
        self.total_frame = QFrame()
        self.total_frame.setFixedHeight(70)
        self.total_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {SAPColors.SUCCESS};
                border-radius: 8px;
            }}
        """)

        total_layout = QVBoxLayout()
        total_layout.setAlignment(Qt.AlignCenter)

        self.total_label = QLabel("Total: €0.00")
        self.total_label.setAlignment(Qt.AlignCenter)
        self.total_label.setStyleSheet(f"""
            QLabel {{
                color: {SAPColors.WHITE};
                font-size: 24px;
                font-weight: 600;
                background: transparent;
            }}
        """)

        total_layout.addWidget(self.total_label)
        self.total_frame.setLayout(total_layout)

        # Actions
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(16)

        cancel_btn = SAPButton("Cancel", "default")
        cancel_btn.clicked.connect(self.reject)

        add_btn = SAPButton("Add to Cart", "primary", "✓")
        add_btn.clicked.connect(self.accept_weight)

        actions_layout.addWidget(cancel_btn)
        actions_layout.addWidget(add_btn)

        # Assembly
        layout.addWidget(info_frame)
        layout.addWidget(weight_label)
        layout.addWidget(self.weight_input)
        layout.addLayout(quick_layout)
        layout.addWidget(self.total_frame)
        layout.addStretch()
        layout.addLayout(actions_layout)

        self.setLayout(layout)
        self.update_total()

    def update_total(self):
        try:
            weight = Decimal(self.weight_input.text())
            self.weight_value = weight
            total = weight * self.product.price
            self.total_label.setText(f"Total: €{total:.2f}")

            if weight > 0:
                self.total_frame.setStyleSheet(f"""
                    QFrame {{
                        background-color: {SAPColors.SUCCESS};
                        border-radius: 8px;
                    }}
                """)
            else:
                self.total_frame.setStyleSheet(f"""
                    QFrame {{
                        background-color: {SAPColors.GREY_6};
                        border-radius: 8px;
                    }}
                """)
        except:
            self.weight_value = Decimal("0")
            self.total_label.setText("Total: €0.00")
            self.total_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {SAPColors.ERROR};
                    border-radius: 8px;
                }}
            """)

    def accept_weight(self):
        if self.weight_value > 0:
            self.accept()
        else:
            QMessageBox.warning(self, "Invalid Weight", "Please enter a valid weight!")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🏢 MAIN APPLICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SAPPOSApplication(QMainWindow):
    """SAP Business POS System"""

    def __init__(self):
        super().__init__()
        self.products = self.load_products()
        self.setup_ui()
        self.connect_signals()

    def load_products(self) -> List[Product]:
        """Load mock product data"""
        return [
            Product(1, "BEV-001", "Coca-Cola 330ml", Decimal("2.50"), "beverages", 150, False),
            Product(2, "BEV-002", "Premium Coffee 250g", Decimal("12.90"), "beverages", 45, False),
            Product(3, "PRD-001", "Fresh Apples", Decimal("3.80"), "produce", 0, True, "kg"),
            Product(4, "PRD-002", "Organic Bananas", Decimal("4.50"), "produce", 0, True, "kg"),
            Product(5, "BAK-001", "Whole Grain Bread", Decimal("2.20"), "bakery", 25, False),
            Product(6, "DAI-001", "Premium Cheese", Decimal("15.90"), "dairy", 0, True, "kg"),
            Product(7, "DAI-002", "Fresh Milk 1L", Decimal("2.80"), "dairy", 80, False),
            Product(8, "MEA-001", "Beef Premium", Decimal("22.50"), "meat", 0, True, "kg"),
        ]

    def setup_ui(self):
        self.setWindowTitle("SAP Business POS System")
        self.setMinimumSize(1600, 900)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main vertical layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Shell bar
        self.shell_bar = SAPShellBar()
        main_layout.addWidget(self.shell_bar)

        # Content area
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Sidebar
        self.sidebar = SAPSidebar()
        content_layout.addWidget(self.sidebar)

        # Products area
        products_widget = QWidget()
        products_widget.setStyleSheet(f"background-color: {SAPColors.GREY_2};")
        products_layout = QVBoxLayout()
        products_layout.setContentsMargins(0, 0, 0, 0)
        products_layout.setSpacing(0)

        # Search bar
        search_bar = self.create_search_bar()
        products_layout.addWidget(search_bar)

        # Products grid
        self.products_scroll = QScrollArea()
        self.products_scroll.setWidgetResizable(True)
        self.products_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {SAPColors.GREY_2};
            }}
            QScrollBar:vertical {{
                background-color: {SAPColors.GREY_3};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {SAPColors.GREY_6};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {SAPColors.BRAND_PRIMARY};
            }}
        """)

        self.products_container = QWidget()
        self.products_grid = QGridLayout()
        self.products_grid.setSpacing(16)
        self.products_grid.setContentsMargins(24, 24, 24, 24)
        self.products_container.setLayout(self.products_grid)

        self.products_scroll.setWidget(self.products_container)
        products_layout.addWidget(self.products_scroll)

        products_widget.setLayout(products_layout)
        content_layout.addWidget(products_widget, 1)

        # Cart panel
        self.cart_panel = SAPCartPanel()
        content_layout.addWidget(self.cart_panel)

        main_layout.addLayout(content_layout)
        central.setLayout(main_layout)

        # Load products
        self.display_products("all")

        # Show maximized
        self.showMaximized()

    def create_search_bar(self) -> QWidget:
        """Create search bar widget"""
        search_widget = QWidget()
        search_widget.setFixedHeight(80)
        search_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {SAPColors.WHITE};
                border-bottom: 1px solid {SAPColors.GREY_4};
            }}
        """)

        layout = QHBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search products by name or SKU...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 12px 20px;
                border: 1px solid {SAPColors.GREY_5};
                border-radius: 8px;
                font-size: 14px;
                background-color: {SAPColors.WHITE};
                color: {SAPColors.GREY_9};
            }}
            QLineEdit:focus {{
                border-color: {SAPColors.BRAND_PRIMARY};
                background-color: {SAPColors.GREY_1};
            }}
        """)
        self.search_input.textChanged.connect(self.filter_products)

        layout.addWidget(self.search_input)
        search_widget.setLayout(layout)

        return search_widget

    def connect_signals(self):
        """Connect all signals"""
        self.sidebar.category_selected.connect(self.display_products)
        self.cart_panel.payment_requested.connect(self.process_payment)

    def display_products(self, category: str):
        """Display products in grid"""
        # Clear grid
        while self.products_grid.count():
            item = self.products_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Filter products
        if category == "all":
            filtered = self.products
        else:
            filtered = [p for p in self.products if p.category == category]

        # Add products to grid
        row, col = 0, 0
        for product in filtered:
            card = SAPProductCard(product)
            card.clicked.connect(self.add_product_to_cart)

            self.products_grid.addWidget(card, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1

        # Add stretch
        self.products_grid.setRowStretch(row + 1, 1)

    def filter_products(self):
        """Filter products by search query"""
        query = self.search_input.text().lower()
        category = self.sidebar.active_category

        # Clear grid
        while self.products_grid.count():
            item = self.products_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Filter products
        filtered = []
        for product in self.products:
            if category != "all" and product.category != category:
                continue
            if query and query not in product.name.lower() and query not in product.sku.lower():
                continue
            filtered.append(product)

        # Add products to grid
        row, col = 0, 0
        for product in filtered:
            card = SAPProductCard(product)
            card.clicked.connect(self.add_product_to_cart)

            self.products_grid.addWidget(card, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1

        # Add stretch
        self.products_grid.setRowStretch(row + 1, 1)

    def add_product_to_cart(self, product: Product):
        """Add product to cart"""
        if product.is_weight:
            dialog = SAPWeightDialog(self, product)
            if dialog.exec() == QDialog.Accepted:
                self.cart_panel.add_item(product, dialog.weight_value)
        else:
            self.cart_panel.add_item(product, Decimal("1"))

    def process_payment(self):
        """Process payment"""
        if not self.cart_panel.cart_items:
            QMessageBox.warning(self, "Empty Cart", "Cart is empty!")
            return

        total = sum(item.total for item in self.cart_panel.cart_items)

        reply = QMessageBox.information(
            self, "Payment Complete",
            f"Payment of €{total:.2f} processed successfully!\n\n"
            f"Items: {len(self.cart_panel.cart_items)}\n"
            f"Thank you for your purchase!",
            QMessageBox.Ok
        )

        if reply == QMessageBox.Ok:
            self.cart_panel.cart_items.clear()
            self.cart_panel.update_display()


def main():
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Set font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Create and show window
    window = SAPPOSApplication()

    # Run
    sys.exit(app.exec())


if __name__ == "__main__":
    main()