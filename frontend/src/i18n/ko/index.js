// Gabungan seluruh kamus terjemahan Korea.
// Setiap halaman punya berkas sendiri agar mudah dirawat.
import common from './common'
import overview from './overview'
import tenders from './tenders'
import tenderdetail from './tenderdetail'
import leads from './leads'
import leaddetail from './leaddetail'
import outreach from './outreach'
import outreachmessage from './outreachmessage'
import automation from './automation'
import reports from './reports'

export default {
  ...common,
  ...overview,
  ...tenders,
  ...tenderdetail,
  ...leads,
  ...leaddetail,
  ...outreach,
  ...outreachmessage,
  ...automation,
  ...reports,
}
