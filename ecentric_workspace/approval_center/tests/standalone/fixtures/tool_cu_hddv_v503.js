// Trich NGUYEN VAN cac ham tinh toan / van ban tu Apps Script "TOOL TAO HDDV & BBNT - ECENTRIC"
// (SCRIPT_VERSION 2026.10.05-PERFORMANCE-V5.0.3, doc ngay 12/11/2026 tu may anh Hoan, chi doc).
// Dung lam "dap an" cho test_contract_kol_tool_cu.py: ban port Python phai ra GIONG HET.
// Chi them stub cho formatDate_/addDays_/stripTime_/normalizePlatform_ (ham tien ich cua Apps Script).

function formatDate_(d, fmt) {
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = String(d.getFullYear());
  if (fmt === 'dd/MM/yyyy') return dd + '/' + mm + '/' + yyyy;
  if (fmt === 'yyyy-MM-dd') return yyyy + '-' + mm + '-' + dd;
  throw new Error('fmt ' + fmt);
}
function addDays_(date, days) { const d = new Date(date.getTime()); d.setDate(d.getDate() + days); return d; }
function stripTime_(date) { return new Date(date.getFullYear(), date.getMonth(), date.getDate()); }
function normalizePlatform_(value) { return String(value || '').toUpperCase().indexOf('SHOPEE') >= 0 ? 'SHOPEE' : 'TIKTOK'; }

function buildWorkTexts_(serviceType, brand, channelUrl, dates, quantity, duration, customDetail, platform) {
platform = normalizePlatform_(platform || 'TikTok');
const dateLines = dates.map(d => formatDate_(d, 'dd/MM/yyyy')).join(', ');
const custom = String(customDetail || '').trim();
if (platform === 'SHOPEE') {
if (serviceType !== 'LIVESTREAM') throw new Error('Shopee hiện chỉ hỗ trợ mẫu Livestream.');
const shopeeDetailLines = [
'- Số lượng: ' + quantityText_(quantity, 'LIVESTREAM') + '.',
'- Các phiên livestream dự kiến diễn ra vào: ' + dateLines + '.',
duration ? '- Thời lượng mỗi phiên: ' + duration + '.' : '- Thời lượng mỗi phiên: theo booking được duyệt.',
'- Số lượng sản phẩm tối thiểu của Bên A được giới thiệu: 01 sản phẩm.'
];
if (custom) shopeeDetailLines.push('- Yêu cầu bổ sung: ' + custom);
return {
titleShort: 'Livestream Shopee',
serviceDisplay: 'Livestream Shopee',
serviceAction: 'phát trực tiếp (livestream)',
objectParagraph: 'Theo các điều khoản và điều kiện của Hợp đồng này, Bên A yêu cầu và Bên B đồng ý cung cấp dịch vụ livestream trên nền tảng Shopee theo chỉ định, yêu cầu của Bên A, cụ thể như sau:',
workParagraph: 'Bên B sẽ phát video trực tiếp (livestream) nhằm giới thiệu, quảng bá sản phẩm ' + brand + ' và gắn link mua hàng (Affiliate) trên nền tảng Shopee, cụ thể là kênh Shopee của Bên B: ' + channelUrl,
workPrefix: '- Bên B sẽ phát video trực tiếp (livestream) nhằm giới thiệu, quảng bá sản phẩm ' + brand + ' và gắn link mua hàng (Affiliate) trên nền tảng Shopee, cụ thể là kênh Shopee của Bên B: ',
detailParagraph: shopeeDetailLines.join('\n'),
durationLabel: '- Thời lượng mỗi phiên: ',
durationDisplay: duration || 'theo booking được duyệt',
minProductLabel: '- Số lượng sản phẩm tối thiểu của bên A được giới thiệu: ',
minProductDisplay: '01 sản phẩm',
resultUsageClause: '- Bên A được quyền sử dụng kết quả buổi phát trực tiếp để phục vụ cho các chiến dịch truyền thông và quảng cáo trong phạm vi Hợp đồng này;',
productInfoClause: '- Cung cấp hoặc chuẩn bị đầy đủ thông tin về sản phẩm được giới thiệu trong buổi phát trực tiếp.',
bbntWorkDescription: 'Quảng bá sản phẩm ' + brand + ' thông qua phát trực tiếp trên nền tảng Shopee tại ' + channelUrl + '.',
bbntWorkDescriptionShort: 'Quảng bá sản phẩm ' + brand + ' thông qua phát trực tiếp trên nền tảng Shopee.',
bbntPaymentDescription: 'Dịch vụ Livestream quảng bá sản phẩm ' + brand + ' trên nền tảng Shopee.',
quantityHeader: 'Số lượng buổi live thực tế'
};
}
if (serviceType === 'VIDEO') {
const detailLines = [
'- Số lượng: ' + quantityText_(quantity, 'VIDEO') + '.',
'- Thời gian đăng tải dự kiến: ' + dateLines + '.',
duration ? '- Thời lượng video: ' + duration + '/video.' : '- Thời lượng video: theo brief được Bên A duyệt.',
'- Số lượng sản phẩm tối thiểu của Bên A được giới thiệu: 01 sản phẩm.'
];
if (custom) detailLines.push('- Yêu cầu bổ sung: ' + custom);
return {
titleShort: 'video',
serviceDisplay: 'Video',
serviceAction: 'đăng tải video',
objectParagraph: 'Theo các điều khoản và điều kiện của Hợp đồng này, Bên A yêu cầu và Bên B đồng ý cung cấp dịch vụ đăng tải video trên nền tảng TikTok theo chỉ định, yêu cầu của Bên A, cụ thể như sau:',
workParagraph: '- Bên B sẽ đăng tải video nhằm giới thiệu, quảng bá sản phẩm ' + brand + ' trên nền tảng TikTok, cụ thể là kênh TikTok của Bên B: ' + channelUrl,
workPrefix: '- Bên B sẽ đăng tải video nhằm giới thiệu, quảng bá sản phẩm ' + brand + ' trên nền tảng TikTok, cụ thể là kênh TikTok của Bên B: ',
detailParagraph: detailLines.join('\n'),
durationLabel: '- Thời lượng video tối thiểu: ',
durationDisplay: duration || 'theo brief được Bên A duyệt',
minProductLabel: '- Số lượng sản phẩm tối thiểu của bên A được giới thiệu: ',
minProductDisplay: '01 sản phẩm',
resultUsageClause: '- Bên A được quyền sử dụng kết quả video do Bên B thực hiện để phục vụ cho các chiến dịch truyền thông và quảng cáo trong phạm vi Hợp đồng này kể từ ngày Bên B bàn giao sản phẩm cho Bên A;',
productInfoClause: '- Cung cấp hoặc chuẩn bị đầy đủ thông tin về sản phẩm được giới thiệu trong video.',
bbntWorkDescription: 'Quảng bá sản phẩm ' + brand + ' thông qua đăng tải video trên nền tảng TikTok tại ' + channelUrl + '.',
bbntWorkDescriptionShort: 'Quảng bá sản phẩm ' + brand + ' thông qua đăng tải video trên nền tảng Tik Tok.',
bbntPaymentDescription: 'Dịch vụ đăng tải video quảng bá sản phẩm ' + brand + ' trên nền tảng TikTok.',
quantityHeader: 'Số lượng video thực tế'
};
}
if (serviceType === 'HYBRID') {
return {
titleShort: 'Livestream và video',
serviceDisplay: 'Livestream và Video',
serviceAction: 'livestream và đăng tải video',
objectParagraph: 'Theo các điều khoản và điều kiện của Hợp đồng này, Bên A yêu cầu và Bên B đồng ý cung cấp dịch vụ livestream và đăng tải video trên nền tảng TikTok theo chỉ định, yêu cầu của Bên A, cụ thể như sau:',
workParagraph: '- Bên B sẽ livestream và/hoặc đăng tải video nhằm giới thiệu, quảng bá sản phẩm ' + brand + ' trên kênh TikTok ' + channelUrl + '.',
workPrefix: '- Bên B sẽ livestream và/hoặc đăng tải video nhằm giới thiệu, quảng bá sản phẩm ' + brand + ' trên kênh TikTok ',
detailParagraph: custom || ('- Thời gian thực hiện dự kiến: ' + dateLines + (duration ? '. Thời lượng: ' + duration + '.' : '.')),
durationLabel: '- Thời lượng thực hiện: ',
durationDisplay: duration || 'theo booking được duyệt',
minProductLabel: '- Số lượng sản phẩm tối thiểu của bên A được giới thiệu: ',
minProductDisplay: '01 sản phẩm',
resultUsageClause: '- Bên A được quyền sử dụng kết quả công việc do Bên B thực hiện để phục vụ cho các chiến dịch truyền thông và quảng cáo trong phạm vi Hợp đồng này;',
productInfoClause: '- Cung cấp hoặc chuẩn bị đầy đủ thông tin về sản phẩm được giới thiệu trong livestream/video.',
bbntWorkDescription: 'Quảng bá sản phẩm ' + brand + ' thông qua livestream và/hoặc video trên nền tảng TikTok tại ' + channelUrl + '.',
bbntWorkDescriptionShort: 'Quảng bá sản phẩm ' + brand + ' thông qua livestream và/hoặc video trên nền tảng Tik Tok.',
bbntPaymentDescription: 'Dịch vụ livestream và video quảng bá sản phẩm ' + brand + ' trên nền tảng TikTok.',
quantityHeader: 'Khối lượng thực tế'
};
}
const detailLines = [
'- Số lượng: ' + quantityText_(quantity, 'LIVESTREAM') + '.',
'- Các phiên livestream dự kiến diễn ra vào: ' + dateLines + '.',
duration ? '- Thời lượng mỗi phiên: ' + duration + '.' : '- Thời lượng mỗi phiên: theo booking được duyệt.',
'- Số lượng sản phẩm tối thiểu của Bên A được giới thiệu: 01 sản phẩm.'
];
if (custom) detailLines.push('- Yêu cầu bổ sung: ' + custom);
return {
titleShort: 'Livestream',
serviceDisplay: 'Livestream',
serviceAction: 'phát trực tiếp (livestream)',
objectParagraph: 'Theo các điều khoản và điều kiện của Hợp đồng này, Bên A yêu cầu và Bên B đồng ý cung cấp dịch vụ livestream trên nền tảng TikTok theo chỉ định, yêu cầu của Bên A, cụ thể như sau:',
workParagraph: '- Bên B sẽ phát video trực tiếp (livestream) nhằm giới thiệu, quảng bá sản phẩm ' + brand + ' và gắn link mua hàng (Affiliate) trên nền tảng TikTok, cụ thể là kênh TikTok của Bên B: ' + channelUrl,
workPrefix: '- Bên B sẽ phát video trực tiếp (livestream) nhằm giới thiệu, quảng bá sản phẩm ' + brand + ' và gắn link mua hàng (Affiliate) trên nền tảng TikTok, cụ thể là kênh TikTok của Bên B: ',
detailParagraph: detailLines.join('\n'),
durationLabel: '- Thời lượng mỗi phiên: ',
durationDisplay: duration || 'theo booking được duyệt',
minProductLabel: '- Số lượng sản phẩm tối thiểu của bên A được giới thiệu: ',
minProductDisplay: '01 sản phẩm',
resultUsageClause: '- Bên A được quyền sử dụng kết quả buổi phát trực tiếp để phục vụ cho các chiến dịch truyền thông và quảng cáo trong phạm vi Hợp đồng này;',
productInfoClause: '- Cung cấp hoặc chuẩn bị đầy đủ thông tin về sản phẩm được giới thiệu trong buổi phát trực tiếp.',
bbntWorkDescription: 'Quảng bá sản phẩm ' + brand + ' thông qua phát trực tiếp trên nền tảng TikTok tại ' + channelUrl + '.',
bbntWorkDescriptionShort: 'Quảng bá sản phẩm ' + brand + ' thông qua phát trực tiếp trên nền tảng Tik Tok.',
bbntPaymentDescription: 'Dịch vụ Livestream quảng bá sản phẩm ' + brand + ' trên nền tảng TikTok.',
quantityHeader: 'Số lượng buổi live thực tế'
};
}

function buildAdvanceServiceTexts_(serviceType, brand, channelUrl, dates, quantity, duration, customDetail, platform) {
const custom = String(customDetail || '').trim();
const count = quantity < 10 ? '0' + quantity : String(quantity);
const allDates = dates.map(date => formatDate_(date, 'dd/MM/yyyy')).join(', ');
const firstDate = formatDate_(dates[0], 'dd/MM/yyyy');
const lastDate = formatDate_(dates[dates.length - 1], 'dd/MM/yyyy');
const durationValue = duration || 'theo booking được Hai Bên thống nhất';

if (serviceType === 'VIDEO') {
return {
subtitle: '(V/v: Cung cấp dịch vụ booking video)',
workParagraph: 'Bên B sẽ đăng tải video nhằm giới thiệu, quảng bá sản phẩm ' + brand + ' trên nền tảng TikTok theo yêu cầu của Bên A.',
customDetailLine: custom,
packageQuantity: count + ' gói',
detailIntro: 'Đăng tải ' + count + ' video giới thiệu sản phẩm. Chi tiết:',
videoDateLine: 'Ngày đăng tải: ' + allDates + ' (dự kiến)',
videoChannelLine: 'Link kênh đăng tải: ' + channelUrl,
videoDurationLine: 'Thời lượng tối thiểu của video: ' + durationValue,
liveSummaryLine: '',
liveDateLine: '',
liveDurationLine: '',
affiliateClause: ''
};
}

if (serviceType === 'HYBRID') {
return {
subtitle: '(V/v: Cung cấp dịch vụ booking video và livestream)',
workParagraph: 'Bên B sẽ đăng tải video và phát trực tiếp (livestream) nhằm giới thiệu, quảng bá sản phẩm ' + brand + ' của Bên A trên nền tảng TikTok.',
customDetailLine: custom,
packageQuantity: count + ' gói',
detailIntro: 'Đăng tải video giới thiệu sản phẩm và thực hiện phiên Livestream. Chi tiết:',
videoDateLine: 'Ngày đăng tải video: ' + firstDate + ' (dự kiến)',
videoChannelLine: 'Link kênh đăng tải: ' + channelUrl,
videoDurationLine: 'Thời lượng tối thiểu của video: ' + durationValue,
liveSummaryLine: 'Thực hiện phiên Livestream. Chi tiết:',
liveDateLine: 'Ngày thực hiện: ' + lastDate,
liveDurationLine: 'Thời lượng tối thiểu của phiên livestream: ' + durationValue + '.',
affiliateClause: 'Trong suốt thời gian livestream, Bên B có trách nhiệm gắn đúng đường dẫn mua hàng (Affiliate) do Bên A cung cấp và giới thiệu tối thiểu 01 sản phẩm của Bên A theo nội dung, kịch bản hoặc hướng dẫn đã được Bên A phê duyệt.'
};
}

return {
subtitle: '(V/v: Cung cấp dịch vụ booking livestream)',
workParagraph: 'Bên B sẽ phát trực tiếp (livestream) nhằm giới thiệu, quảng bá sản phẩm ' + brand + ' của Bên A và gắn link mua hàng (Affiliate) trên nền tảng TikTok, cụ thể là kênh TikTok của Bên B: ' + channelUrl,
customDetailLine: custom,
packageQuantity: count + ' gói',
detailIntro: 'Thực hiện ' + count + ' phiên Livestream. Chi tiết:',
videoDateLine: '',
videoChannelLine: '',
videoDurationLine: '',
liveSummaryLine: '',
liveDateLine: 'Ngày thực hiện: ' + allDates,
liveDurationLine: 'Thời lượng tối thiểu của mỗi phiên livestream: ' + durationValue + '.',
affiliateClause: 'Trong suốt thời gian livestream, Bên B có trách nhiệm gắn đúng đường dẫn mua hàng (Affiliate) do Bên A cung cấp và giới thiệu tối thiểu 01 sản phẩm của Bên A theo nội dung, kịch bản hoặc hướng dẫn đã được Bên A phê duyệt.'
};
}

function quantityText_(quantity, serviceType) {
const num = quantity < 10 ? '0' + quantity : String(quantity);
if (serviceType === 'VIDEO') return num + ' video';
if (serviceType === 'HYBRID') return num + ' hạng mục';
return num + ' buổi';
}

function calculateMoney_(creatorType, amount, amountType, tncRate, vatRate) {
if (creatorType === 'HOUSEHOLD') {
const total = Math.round(amount);
return {preVat: total, vat: 0, total, gross: total, tax: 0, net: total};
}
if (creatorType === 'COMPANY') {
let preVat, total;
if (amountType === 'AFTER_VAT') {
total = Math.round(amount);
preVat = Math.round(total / (1 + vatRate));
} else {
preVat = Math.round(amount);
total = preVat + Math.round(preVat * vatRate);
}
const vat = total - preVat;
return {preVat, vat, total, gross: total, tax: vat, net: total};
}
let gross, net;
if (amountType === 'NET_AFTER_TNCN') {
net = Math.round(amount);
gross = Math.round(net / (1 - tncRate));
} else {
gross = Math.round(amount);
net = gross - Math.round(gross * tncRate);
}
const tax = gross - net;
return {gross, tax, net, preVat: gross, vat: 0, total: net};
}

function numberToVietnamese_(value) {
let n = Math.round(Number(value));
if (!isFinite(n)) return '';
if (n === 0) return 'Không đồng';
if (n < 0) return 'Âm ' + numberToVietnamese_(-n).toLowerCase();
const units = ['', 'nghìn', 'triệu', 'tỷ', 'nghìn tỷ', 'triệu tỷ'];
const groups = [];
while (n > 0) {
groups.unshift(n % 1000);
n = Math.floor(n / 1000);
}
const parts = [];
groups.forEach((group, index) => {
if (!group) return;
const full = parts.length > 0 && group < 100;
const words = readThreeDigits_(group, full);
const unitIndex = groups.length - index - 1;
parts.push(words + (units[unitIndex] ? ' ' + units[unitIndex] : ''));
});
const result = parts.join(' ').replace(/\s+/g, ' ').trim() + ' đồng';
return result.charAt(0).toUpperCase() + result.slice(1);
}

function readThreeDigits_(number, full) {
const digits = ['không', 'một', 'hai', 'ba', 'bốn', 'năm', 'sáu', 'bảy', 'tám', 'chín'];
const hundred = Math.floor(number / 100);
const tens = Math.floor((number % 100) / 10);
const unit = number % 10;
const words = [];
if (hundred || full) words.push(digits[hundred], 'trăm');
if (tens > 1) {
words.push(digits[tens], 'mươi');
if (unit === 1) words.push('mốt');
else if (unit === 4) words.push('tư');
else if (unit === 5) words.push('lăm');
else if (unit) words.push(digits[unit]);
} else if (tens === 1) {
words.push('mười');
if (unit === 5) words.push('lăm');
else if (unit) words.push(digits[unit]);
} else if (unit) {
if (hundred || full) words.push('lẻ');
words.push(digits[unit]);
}
return words.join(' ');
}

function resolvePartyCode_(creatorType, displayName, manualCode) {
const code = String(manualCode || '').trim().toUpperCase();
if (creatorType === 'HOUSEHOLD') {
const isShortManualCode = /^[A-Z0-9]{2,8}$/.test(code) && code !== 'HKD';
const householdName = String(displayName || '').replace(/^\s*HỘ\s+KINH\s+DOANH\s*[-:]?\s*/i, '');
return isShortManualCode ? code : companyCode_(householdName || displayName);
}
if (creatorType === 'COMPANY') {
const isShortManualCode = /^[A-Z0-9]{2,6}$/.test(code) && code !== 'CONGTY';
return isShortManualCode ? code : companyCode_(displayName);
}
return code || initials_(displayName);
}

function companyCode_(name) {
const ignoredWords = {
CONG: true, TY: true, CO: true, PHAN: true, TNHH: true, TRACH: true, NHIEM: true, HUU: true, HAN: true,
MOT: true, THANH: true, VIEN: true, THUONG: true, MAI: true, VA: true, DICH: true, VU: true
};
const words = removeDiacritics_(String(name || ''))
.toUpperCase()
.split(/[^A-Z0-9]+/)
.filter(word => word && !ignoredWords[word]);

if (!words.length) return initials_(name);
if (words.length === 1) return words[0].substring(0, 8);
return words.map(word => word.charAt(0)).join('').substring(0, 8);
}

function initials_(name) {
return removeDiacritics_(String(name || ''))
.split(/\s+/)
.filter(Boolean)
.map(word => word.charAt(0))
.join('')
.toUpperCase() || 'CREATOR';
}

function removeDiacritics_(text) {
return String(text || '')
.normalize('NFD')
.replace(/[̀-ͯ]/g, '')
.replace(/đ/g, 'd')
.replace(/Đ/g, 'D');
}

function normalizeKey_(value) {
return removeDiacritics_(String(value == null ? '' : value))
.trim()
.replace(/\s+/g, ' ')
.toUpperCase();
}

function combineBankBranch_(bank, branch) {
const b = String(bank || '').trim();
const br = String(branch || '').trim();
if (!br) return b;
if (/\b(cn|chi nhánh)\b/i.test(br)) return b + ' - ' + br;
return b + ' - CN ' + br;
}

function normalizeVietnamAddress_(value) {
const address = String(value == null ? '' : value)
.trim()
.replace(/\s+,/g, ',')
.replace(/,{2,}/g, ',')
.replace(/\s{2,}/g, ' ')
.replace(/[,.\s]+$/g, '');
if (!address) return '';
const normalized = normalizeKey_(address);
return normalized.indexOf('VIET NAM') >= 0 ? address : address + ', Việt Nam';
}

function stripHonorific_(name) {
return String(name || '').replace(/^\s*(ông|bà|anh|chị)\s+/i, '').trim();
}

function formatMoney_(value) {
return String(Math.round(value)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

function businessDateBefore_(input, boundary, businessDays, holidays) {
let date = input ? stripTime_(input) : addDays_(boundary, -1);
if (date >= stripTime_(boundary)) date = addDays_(boundary, -1);
date = moveToBusinessDay_(date, -1, holidays);
let remaining = Math.max(1, businessDays) - 1;
while (remaining-- > 0) date = moveToBusinessDay_(addDays_(date, -1), -1, holidays);
return date;
}

function businessDateAfter_(input, boundary, businessDays, holidays) {
let date = input ? stripTime_(input) : addDays_(boundary, 1);
if (date <= stripTime_(boundary)) date = addDays_(boundary, 1);
date = moveToBusinessDay_(date, 1, holidays);
let remaining = Math.max(1, businessDays) - 1;
while (remaining-- > 0) date = moveToBusinessDay_(addDays_(date, 1), 1, holidays);
return date;
}

function moveToBusinessDay_(date, direction, holidays) {
let d = stripTime_(date);
while (d.getDay() === 0 || d.getDay() === 6 || holidays[formatDate_(d, 'yyyy-MM-dd')]) {
d = addDays_(d, direction);
}
return d;
}

// ---- runner: doc ca kiem tu stdin (JSON), tra ket qua JSON ----
const D = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = {};
out.work = input.work.map(c => buildWorkTexts_(c.kind, c.brand, c.url, c.dates.map(D), c.q, c.dur, c.custom, c.platform));
out.adv = input.work.filter(c => c.platform !== 'Shopee').map(c => buildAdvanceServiceTexts_(c.kind, c.brand, c.url, c.dates.map(D), c.q, c.dur, c.custom, c.platform));
out.words = input.numbers.map(numberToVietnamese_);
out.money = input.numbers.map(formatMoney_);
out.calc = input.calc.map(c => calculateMoney_(c.type, c.amount, c.amountType, c.tnc, c.vat));
out.party = input.party.map(c => resolvePartyCode_(c.type, c.name, c.manual));
out.bank = input.bank.map(c => combineBankBranch_(c[0], c[1]));
out.addr = input.addr.map(normalizeVietnamAddress_);
out.honor = input.honor.map(stripHonorific_);
const hol = {}; input.holidays.forEach(h => { hol[h] = true; });
out.before = input.dates.map(c => formatDate_(businessDateBefore_(c.input ? D(c.input) : null, D(c.boundary), c.n, hol), 'yyyy-MM-dd'));
out.after = input.dates.map(c => formatDate_(businessDateAfter_(c.input ? D(c.input) : null, D(c.boundary), c.n, hol), 'yyyy-MM-dd'));
process.stdout.write(JSON.stringify(out));
