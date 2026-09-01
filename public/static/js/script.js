/* ==========================================================
   Medicine Inventory Management System
   script.js
========================================================== */

document.addEventListener("DOMContentLoaded", function () {

    console.log("Medicine Inventory Management System Loaded");

    /* ==============================================
       Auto Hide Flash Messages
    ============================================== */

    setTimeout(function () {

        let alerts = document.querySelectorAll(".alert");

        alerts.forEach(function (alert) {

            alert.style.transition = "0.5s";

            alert.style.opacity = "0";

            setTimeout(function () {

                alert.remove();

            }, 500);

        });

    }, 3000);


    /* ==============================================
       Expiry Date Warning
    ============================================== */

    let expiryInput = document.getElementById("expiry_date");

    if (expiryInput) {

        expiryInput.addEventListener(

            "change",

            checkExpiryWarning

        );

    }


    /* ==============================================
       Mobile Sidebar Drawer
    ============================================== */

    let sidebar = document.getElementById("sidebar");
    let toggleBtn = document.getElementById("mobileNavToggle");
    let backdrop = document.getElementById("sidebarBackdrop");

    function openSidebar() {
        if (sidebar) sidebar.classList.add("open");
        if (backdrop) backdrop.classList.add("show");
    }

    function closeSidebar() {
        if (sidebar) sidebar.classList.remove("open");
        if (backdrop) backdrop.classList.remove("show");
    }

    if (toggleBtn) {
        toggleBtn.addEventListener("click", function () {
            if (sidebar && sidebar.classList.contains("open")) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });
    }

    if (backdrop) {
        backdrop.addEventListener("click", closeSidebar);
    }

});


/* ==========================================================
   ADD MEDICINE TO CART
========================================================== */

function addProduct(btn) {

    if (typeof addToCart !== "function") {

        console.error("addToCart() function not found.");

        return;

    }

    addToCart(

        parseInt(btn.dataset.id),

        btn.dataset.name,

        parseFloat(btn.dataset.price),

        parseInt(btn.dataset.stock)

    );

}


/* ==========================================================
   Confirm Delete
========================================================== */

function confirmDelete(message) {

    if (!message) {

        message =

            "Are you sure you want to delete this record?";

    }

    return confirm(message);

}


/* ==========================================================
   Search Table
========================================================== */

function searchTable(inputId, tableId, column) {

    let input = document.getElementById(inputId);

    let filter = input.value.toUpperCase();

    let table = document.getElementById(tableId);

    let tr = table.getElementsByTagName("tr");

    for (let i = 1; i < tr.length; i++) {

        let td = tr[i].getElementsByTagName("td")[column];

        if (td) {

            let txt = td.textContent || td.innerText;

            if (

                txt.toUpperCase().indexOf(filter) > -1

            ) {

                tr[i].style.display = "";

            }

            else {

                tr[i].style.display = "none";

            }

        }

    }

}


/* ==========================================================
   Preview Medicine Image
========================================================== */

function previewImage(input, previewId) {

    if (input.files && input.files[0]) {

        let reader = new FileReader();

        reader.onload = function (e) {

            document.getElementById(previewId).src =

                e.target.result;

        };

        reader.readAsDataURL(input.files[0]);

    }

}


/* ==========================================================
   Open Modal
========================================================== */

function openModal(id) {

    document.getElementById(id).style.display = "block";

}


/* ==========================================================
   Close Modal
========================================================== */

function closeModal(id) {

    document.getElementById(id).style.display = "none";

}


/* ==========================================================
   Close Modal On Outside Click
========================================================== */

window.onclick = function (event) {

    let modals = document.querySelectorAll(".modal");

    modals.forEach(function (modal) {

        if (event.target === modal) {

            modal.style.display = "none";

        }

    });

};


/* ==========================================================
   Print Invoice
========================================================== */

function printInvoice() {

    window.print();

}
/* ==========================================================
   Loading Button
========================================================== */

function loadingButton(button) {

    button.disabled = true;

    button.innerHTML =
        '<i class="fa fa-spinner fa-spin"></i> Processing...';

}


/* ==========================================================
   Reset Form
========================================================== */

function resetForm(formId) {

    let form = document.getElementById(formId);

    if (form) {

        form.reset();

    }

}


/* ==========================================================
   Toggle Password
========================================================== */

function togglePassword(inputId, icon) {

    let input = document.getElementById(inputId);

    if (!input) return;

    if (input.type === "password") {

        input.type = "text";

        icon.classList.remove("fa-eye");

        icon.classList.add("fa-eye-slash");

    } else {

        input.type = "password";

        icon.classList.remove("fa-eye-slash");

        icon.classList.add("fa-eye");

    }

}


/* ==========================================================
   Simple Notification
========================================================== */

function showNotification(message) {

    alert(message);

}


/* ==========================================================
   Medicine Expiry Validation
========================================================== */

function validateExpiryDate() {

    let expiry = document.getElementById("expiry_date");

    if (!expiry || expiry.value === "") {

        return true;

    }

    let expiryDate = new Date(expiry.value);

    let today = new Date();

    today.setHours(0, 0, 0, 0);

    if (expiryDate < today) {

        alert("This medicine has already expired.");

        expiry.focus();

        return false;

    }

    return true;

}


/* ==========================================================
   Medicine Expiry Warning
========================================================== */

function checkExpiryWarning() {

    let expiry = document.getElementById("expiry_date");

    if (!expiry || expiry.value === "") {

        return;

    }

    let expiryDate = new Date(expiry.value);

    let today = new Date();

    today.setHours(0, 0, 0, 0);

    let days = Math.ceil(

        (expiryDate - today) /

        (1000 * 60 * 60 * 24)

    );

    if (days < 0) {

        showNotification(

            "⚠ This medicine is already expired."

        );

    }

    else if (days <= 30) {

        showNotification(

            "⚠ Warning: This medicine will expire within 30 days."

        );

    }

}


/* ==========================================================
   Days Remaining
========================================================== */

function getDaysRemaining(expiryDate) {

    if (!expiryDate) {

        return null;

    }

    let today = new Date();

    today.setHours(0, 0, 0, 0);

    let expiry = new Date(expiryDate);

    expiry.setHours(0, 0, 0, 0);

    return Math.ceil(

        (expiry - today) /

        (1000 * 60 * 60 * 24)

    );

}


/* ==========================================================
   Medicine Status
========================================================== */

function getMedicineStatus(expiryDate) {

    let days = getDaysRemaining(expiryDate);

    if (days === null) {

        return "No Expiry";

    }

    if (days < 0) {

        return "Expired";

    }

    if (days <= 30) {

        return "Expiring Soon";

    }

    return "Safe";

}


/* ==========================================================
   Stock Warning
========================================================== */

function checkLowStock(stock) {

    if (stock <= 5) {

        showNotification(

            "⚠ Low Stock Alert!"

        );

    }

}


/* ==========================================================
   Form Validation
========================================================== */

function validateMedicineForm() {

    if (!validateExpiryDate()) {

        return false;

    }

    return true;

}
